"""Build the tidy tables from CSVs pulled through the Planning Center connector.

Alternative to fetch_pco.py + build.py when direct API access isn't available.
The CSVs live in data/connector/ (see data/connector/AGENT_RULES.md for how
they were pulled); this script writes the same data/tidy tables analyze.py reads.
Giving is not available through the connector account, so no gifts are written.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd

from config import DATA_DIR, TIDY_DIR, TZ, event_area

SRC = DATA_DIR / "connector"
LOCAL = ZoneInfo(TZ)


def read_all(pattern: str) -> pd.DataFrame:
    files = sorted(SRC.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f, dtype=str) for f in files], ignore_index=True)


def to_local(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, utc=True).dt.tz_convert(LOCAL)


def main():
    TIDY_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Check-ins -------------------------------------------------------
    ci = read_all("checkins/2*.csv").drop_duplicates("checkin_id")
    periods = read_all("checkins/periods_*.csv").drop_duplicates("event_period_id")
    # Check-Ins "event periods" for Sunday events open on Saturday afternoon, so a
    # period starting Saturday 3pm or later belongs to Sunday.
    loc = to_local(periods["starts_at"])
    sat_pm = (loc.dt.weekday == 5) & (loc.dt.hour >= 15)
    periods["local"] = loc.where(~sat_pm, loc + pd.Timedelta(days=1))
    ci = ci.merge(periods[["event_period_id", "event_id", "local"]], on="event_period_id", how="left")
    missing = ci["local"].isna().sum()
    if missing:
        print(f"warning: {missing} check-ins have no event period date; dropped")
    ci = ci.dropna(subset=["local"])
    ci["date"] = ci["local"].dt.date.astype(str)
    ci["service_time"] = None  # periods don't record which service someone attended
    guest = ci["person_id"].isna() | (ci["one_time_guest"].str.lower() == "true")
    pd.DataFrame({"date": ci.loc[guest, "date"], "event_id": ci.loc[guest, "event_id"]}).to_csv(
        TIDY_DIR / "guests.csv", index=False)
    ci = ci[~guest]
    act = [pd.DataFrame({
        "person_id": ci["person_id"], "date": ci["date"], "source": "checkin",
        "kind": ci["kind"].str.lower(), "event_id": ci["event_id"],
        "service_time": ci["service_time"], "ref": "check_ins/" + ci["checkin_id"]})]

    names = pd.read_csv(SRC / "checkin_events.csv", dtype=str)
    ev = pd.DataFrame({"event_id": sorted(set(ci["event_id"].dropna()))}).merge(names, how="left")
    ev["name"] = ev["name"].fillna("Unknown event")
    ev["area"] = ev["name"].map(event_area)
    ev.to_csv(TIDY_DIR / "events.csv", index=False)

    ft = read_all("first_time/*.csv")
    if len(ft):
        ft = ft.drop_duplicates("checkin_id").merge(periods[["event_period_id", "local"]], on="event_period_id", how="left")
        ft = ft.dropna(subset=["person_id", "local"])
        pd.DataFrame({"person_id": ft["person_id"], "date": ft["local"].dt.date.astype(str)}).to_csv(
            TIDY_DIR / "first_time.csv", index=False)

    # ---- Groups ----------------------------------------------------------
    ge = read_all("group_events/group_events.csv")
    ga = read_all("group_att/*.csv")
    if len(ge):
        ge["date"] = to_local(ge["starts_at"]).dt.date.astype(str)
        counts = ga.groupby("group_event_id").size() if len(ga) else pd.Series(dtype=int)
        out = ge[["group_event_id", "group_id", "date"]].assign(
            canceled=False, attendees=ge["group_event_id"].map(counts).fillna(0).astype(int))
        out.to_csv(TIDY_DIR / "group_events.csv", index=False)
        if len(ga):
            ga = ga.drop_duplicates("attendance_id").merge(ge[["group_event_id", "group_id", "date"]], on="group_event_id")
            act.append(pd.DataFrame({
                "person_id": ga["person_id"], "date": ga["date"], "source": "group", "kind": ga["role"],
                "event_id": ga["group_id"], "service_time": None, "ref": "groups/attendance/" + ga["attendance_id"]}))

    # ---- Serving (Services, confirmed only) ------------------------------
    plans = read_all("plans/plans.csv")
    pp = read_all("plan_people/*.csv")
    if len(pp):
        plans["date"] = to_local(plans["sort_date"]).dt.date.astype(str)
        pp = pp.drop_duplicates("plan_person_id").merge(plans[["plan_id", "date"]], on="plan_id")
        pp = pp[pp["status"].str.lower().str.startswith("c")]
        act.append(pd.DataFrame({
            "person_id": pp["person_id"], "date": pp["date"], "source": "serve", "kind": "confirmed",
            "event_id": pp["team_id"], "service_time": None, "ref": "services/plan_people/" + pp["plan_person_id"]}))

    activity = pd.concat(act, ignore_index=True).dropna(subset=["person_id", "date"])
    activity.to_csv(TIDY_DIR / "activity.csv", index=False)
    print(activity.groupby("source").size().to_string())

    # ---- People & households --------------------------------------------
    people = read_all("people/*.csv").drop_duplicates("person_id")
    hh = read_all("households/*.csv").drop_duplicates(["household_id", "person_id"])
    if len(hh):
        hh[["household_id", "person_id"]].assign(primary_contact_id=None).to_csv(
            TIDY_DIR / "households.csv", index=False)
    if len(people):
        if len(hh) and "birthdate" in hh:
            bd = hh.dropna(subset=["birthdate"]).drop_duplicates("person_id").set_index("person_id")["birthdate"]
            people["birthdate"] = people["birthdate"].fillna(people["person_id"].map(bd))
        for col in ["created_at", "inactivated_at"]:
            if col in people:
                people[col] = to_local(people[col]).dt.date.astype(str).replace("NaT", None)
        people["campus_id"] = "17728"
        people.to_csv(TIDY_DIR / "people.csv", index=False)
    pd.DataFrame([{"campus_id": "17728", "campus": "Shreveport Campus"}]).to_csv(TIDY_DIR / "campuses.csv", index=False)
    for name in ["group_members", "headcounts", "groups"]:
        p = TIDY_DIR / f"{name}.csv"
        if not p.exists():
            pd.DataFrame().to_csv(p, index=False)


if __name__ == "__main__":
    main()
