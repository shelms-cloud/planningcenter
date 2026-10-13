"""Year-over-year retention from the full Check-Ins history (Jan 2023 onward).

For each fall (91 days ending Oct 13 of year Y) it takes everyone who was a
regular attender (6+ check-in days) and asks where they were a year later:
still regular, still around but not regular, or gone quiet (no check-in in
the last 90 days). It also counts genuine first-time guests per year.

Check-ins only, so every year is measured the same way: group attendance and
serving rosters were only pulled from mid-2025, so mixing them in would make
2025-26 look better than earlier years for reasons that have nothing to do
with people. Writes out/yearly.json (aggregates only).
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

import config as C
from build_connector import SRC, read_all, to_local

AS_OF = dt.date(2026, 10, 13)
WINDOW = 91
REGULAR_DAYS = 6
QUIET_DAYS = 90
FIRST_LOOKBACK = 365  # a "first visit" needs at least a year of clean history before it
NEWCOMER_FOLLOW = 182  # how long a first-timer gets to become regular


def load_checkins() -> pd.DataFrame:
    ci = pd.concat([read_all("checkins_hist/2*.csv"), read_all("checkins/2*.csv")]).drop_duplicates("checkin_id")
    periods = pd.concat([read_all("checkins_hist/periods_*.csv"),
                         read_all("checkins/periods_*.csv")]).drop_duplicates("event_period_id").reset_index(drop=True)
    loc = to_local(periods["starts_at"])
    sat_pm = (loc.dt.weekday == 5) & (loc.dt.hour >= 15)
    periods["date"] = loc.where(~sat_pm, loc + pd.Timedelta(days=1)).dt.date
    # "Sunday ..." events sometimes open days early (2023 Dream Team periods start on
    # Thursday), so date them to the Sunday they serve.
    names = pd.read_csv(SRC / "checkin_events.csv", dtype=str)
    periods = periods.merge(names, on="event_id", how="left")
    sunday = periods["name"].fillna("").str.lower().str.startswith("sunday")
    loc = to_local(periods["starts_at"])
    to_sun = loc.dt.date.map(lambda d: d + dt.timedelta(days=(6 - d.weekday()) % 7))
    periods.loc[sunday, "date"] = to_sun[sunday]
    ci = ci.merge(periods[["event_period_id", "event_id", "name", "date"]], on="event_period_id", how="left")
    missing = int(ci["date"].isna().sum())
    ci = ci.dropna(subset=["date"])
    ci = ci[ci["person_id"].notna() & (ci["one_time_guest"].str.lower() != "true")]
    ci["area"] = ci["name"].fillna("").map(C.event_area)
    ci.attrs["missing_dates"] = missing
    ci.attrs["unnamed_events"] = sorted(set(ci.loc[ci["name"].isna(), "event_id"]))
    return ci


def other_activity(ci: pd.DataFrame) -> pd.DataFrame:
    """Non-check-in activity that reaches back to 2023 for every year alike: forms the
    person submitted, event registrations, and a child in their household being checked in."""
    t = C.TIDY_DIR
    act = pd.read_csv(t / "activity.csv", dtype=str)
    out = [act[act["source"].isin(["form", "register"])][["person_id", "date", "source"]]]
    hh = pd.read_csv(t / "households.csv", dtype=str)
    people = pd.read_csv(t / "people.csv", dtype=str)
    age = (pd.Timestamp(AS_OF) - pd.to_datetime(people.set_index("person_id")["birthdate"], errors="coerce")).dt.days / 365.25
    kids = set(age[age < 18].index)
    kci = ci[ci["person_id"].isin(kids) & (ci["kind"].str.lower() != "volunteer")][["person_id", "date"]]
    kci = kci.merge(hh[["household_id", "person_id"]], on="person_id")[["household_id", "date"]]
    adults = hh[~hh["person_id"].isin(kids)][["household_id", "person_id"]]
    cred = kci.merge(adults, on="household_id")[["person_id", "date"]].assign(source="household")
    out.append(cred.assign(date=cred["date"].astype(str)))
    o = pd.concat(out, ignore_index=True).drop_duplicates()
    o["date"] = pd.to_datetime(o["date"]).dt.date
    return o


def days_in(att: pd.DataFrame, start: dt.date, end: dt.date) -> pd.Series:
    w = att[(att["date"] >= start) & (att["date"] <= end)]
    return w.groupby("person_id")["date"].nunique()


def cohort(att, act, kids_ids, year, act_checkins=None):
    ref = dt.date(year, 10, 13)
    base = days_in(att, ref - dt.timedelta(days=WINDOW - 1), ref)
    regs = set(base[base >= REGULAR_DAYS].index)
    later = dt.date(year + 1, 10, 13)
    after = days_in(att, later - dt.timedelta(days=WINDOW - 1), later)
    recent = set(act[(act["date"] > later - dt.timedelta(days=QUIET_DAYS)) & (act["date"] <= later)]["person_id"])
    if act_checkins is not None:
        ci_recent = set(act_checkins[(act_checkins["date"] > later - dt.timedelta(days=QUIET_DAYS)) &
                                     (act_checkins["date"] <= later)]["person_id"])

    def split(ids):
        n = len(ids)
        still = sum(1 for p in ids if after.get(p, 0) >= REGULAR_DAYS)
        gone = sum(1 for p in ids if p not in recent)
        extra = {}
        if act_checkins is not None:
            g2 = sum(1 for p in ids if p not in ci_recent)
            extra = {"gone_quiet_checkins_only": g2, "kept_in_touch_only_by_forms_registrations_or_kids": g2 - gone}
        return {**extra, "regulars": n, "still_regular": still, "around_not_regular": n - still - gone, "gone_quiet": gone,
                "still_regular_pct": round(100 * still / n, 1) if n else None,
                "gone_quiet_pct": round(100 * gone / n, 1) if n else None}

    return {"from": str(ref), "to": str(later), "everyone": split(sorted(regs)),
            "kids_checkins": split(sorted(regs & kids_ids)),
            "everyone_else": split(sorted(regs - kids_ids))}


def newcomers(att, history_start):
    first = att.groupby("person_id")["date"].min()
    first = first[first >= history_start + dt.timedelta(days=FIRST_LOOKBACK)]
    out = {}
    for year in range(2024, AS_OF.year + 1):
        ids = first[(first >= dt.date(year, 1, 1)) & (first <= dt.date(year, 12, 31))]
        ytd = ids[ids <= dt.date(year, AS_OF.month, AS_OF.day)]
        mature = ids[ids <= AS_OF - dt.timedelta(days=NEWCOMER_FOLLOW)]
        became_regular = 0
        for p, d in mature.items():
            follow = att[(att["person_id"] == p) & (att["date"] >= d) &
                         (att["date"] < d + dt.timedelta(days=NEWCOMER_FOLLOW))]["date"]
            dates = sorted(set(follow))
            # regular at any point in the 6 months: 6+ days inside some 91-day stretch
            if any(sum(1 for x in dates if s <= x < s + dt.timedelta(days=WINDOW)) >= REGULAR_DAYS for s in dates):
                became_regular += 1
        out[str(year)] = {"first_timers": int(len(ids)), "first_timers_jan1_to_oct13": int(len(ytd)),
                          "with_6_months": int(len(mature)), "became_regular_within_6_months": became_regular,
                          "became_regular_pct": round(100 * became_regular / len(mature), 1) if len(mature) else None}
    return out


def main():
    ci = load_checkins()
    act = ci[ci["area"] != "ignore"]  # any real check-in keeps someone from being "gone quiet"
    checkins_only = act[["person_id", "date"]]
    extra = other_activity(act)
    act = pd.concat([checkins_only, extra[["person_id", "date"]]], ignore_index=True)
    att = act[act["area"] != "special"][["person_id", "date", "area", "name"]]
    history_start = dt.date(2023, 1, 1)  # first day of the pulled history
    kids_ids = set(att.loc[att["area"] == "kids", "person_id"])
    by_year = att.assign(year=pd.to_datetime(att["date"]).dt.year)
    out = {
        "as_of": str(AS_OF), "history_start": str(history_start),
        "checkins_used": int(len(ci)), "checkins_without_date_dropped": ci.attrs["missing_dates"],
        "event_ids_without_name": ci.attrs["unnamed_events"],
        "definitions": {
            "regular": f"{REGULAR_DAYS}+ distinct check-in days in the {WINDOW} days ending Oct 13",
            "gone_quiet": (f"no activity in the {QUIET_DAYS} days ending Oct 13 a year later: no check-in, no check-in "
                           "of a child in their household, no form submitted, no event registration"),
            "first_timer": f"first check-in ever, with at least {FIRST_LOOKBACK} days of history before it",
            "kids_checkins": "people who were ever checked in to a kids event (mostly children)",
        },
        "cohorts": [cohort(att, act, kids_ids, y, checkins_only) for y in range(2023, AS_OF.year)],
        "other_activity_rows": extra.groupby("source").size().to_dict(),
        "newcomers": newcomers(att, history_start),
        "people_checked_in_by_year": {str(y): int(g["person_id"].nunique()) for y, g in by_year.groupby("year")},
        "adult_service_checkins_by_year": {
            str(y): int(len(g)) for y, g in by_year[by_year["name"] == "Sunday Experience"].groupby("year")},
    }
    (C.OUT_DIR / "yearly.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
