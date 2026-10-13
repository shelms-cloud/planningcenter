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

from config import AS_OF, DATA_DIR, TIDY_DIR, TZ, event_area

SRC = DATA_DIR / "connector"
LOCAL = ZoneInfo(TZ)
# Internal staff paperwork submitted through People forms; not a sign of church involvement.
STAFF_FORMS = (r"purchase order|check request|time sheet|reimburs|graphic request|facilities request|time off|"
               r"vacation/sick|video request|mileage|communications request|staff website|receipts|"
               r"intern oversight|budget request|reserve a room|employment|student event schedules|"
               r"new building prep|admin team brunch")


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

    # ---- Forms the person submitted (staff paperwork excluded) ------------
    forms = read_all("forms/forms.csv")
    subs = read_all("forms/batch_*.csv")
    if len(subs):
        subs = subs.drop_duplicates("submission_id").merge(forms[["form_id", "name"]], on="form_id", how="left")
        staff = subs["name"].fillna("").str.contains(STAFF_FORMS, case=False, regex=True)
        print(f"forms: {len(subs)} submissions, {int(staff.sum())} on staff/admin forms excluded")
        subs = subs[~staff]
        act.append(pd.DataFrame({
            "person_id": subs["person_id"], "date": to_local(subs["created_at"]).dt.date.astype(str),
            "source": "form", "kind": None, "event_id": subs["form_id"], "service_time": None,
            "ref": "people/form_submissions/" + subs["submission_id"]}))

    # ---- Event registrations (Registrations app) --------------------------
    reg = read_all("registrations/batch_*.csv")
    if len(reg):
        reg = reg.drop_duplicates("attendee_id").dropna(subset=["person_id"])
        act.append(pd.DataFrame({
            "person_id": reg["person_id"], "date": to_local(reg["created_at"]).dt.date.astype(str),
            "source": "register", "kind": None, "event_id": reg["signup_id"], "service_time": None,
            "ref": "registrations/attendees/" + reg["attendee_id"]}))

    activity = pd.concat(act, ignore_index=True).dropna(subset=["person_id", "date"])

    # ---- Staff notes: who on staff touched whom (note text not pulled) ----
    notes = read_all("notes/notes_*.csv")
    if len(notes):
        notes = notes.drop_duplicates("note_id").dropna(subset=["person_id"])
        cats = read_all("notes/note_categories.csv").rename(columns={"name": "category"})
        notes = notes.merge(cats, left_on="note_category_id", right_on="category_id", how="left")
        notes["date"] = to_local(notes["created_at"]).dt.date.astype(str)
        notes[["person_id", "date", "category", "created_by_id"]].to_csv(TIDY_DIR / "staff_notes.csv", index=False)

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
        # A child's check-in also counts as activity for the adults in the child's
        # household: a parent who drops kids off is at church even if not checked in.
        if len(hh):
            age = (pd.Timestamp(AS_OF) - pd.to_datetime(people.set_index("person_id")["birthdate"], errors="coerce")).dt.days / 365.25
            kids = set(age[age < 18].index)
            adults = hh[~hh["person_id"].isin(kids)][["household_id", "person_id"]]
            kci = activity[(activity["source"] == "checkin") & activity["person_id"].isin(kids)
                           & (activity["kind"] != "volunteer")]
            kci = kci.merge(hh[["household_id", "person_id"]], on="person_id")[["household_id", "date", "event_id"]]
            cred = kci.merge(adults, on="household_id").drop_duplicates(["person_id", "date"])
            activity = pd.concat([activity, pd.DataFrame({
                "person_id": cred["person_id"], "date": cred["date"], "source": "household", "kind": "child checked in",
                "event_id": cred["event_id"], "service_time": None, "ref": "households/" + cred["household_id"]})],
                ignore_index=True)
    activity.to_csv(TIDY_DIR / "activity.csv", index=False)
    print(activity.groupby("source").size().to_string())
    pd.DataFrame([{"campus_id": "17728", "campus": "Shreveport Campus"}]).to_csv(TIDY_DIR / "campuses.csv", index=False)
    for name in ["group_members", "headcounts", "groups"]:
        p = TIDY_DIR / f"{name}.csv"
        if not p.exists():
            pd.DataFrame().to_csv(p, index=False)


if __name__ == "__main__":
    main()
