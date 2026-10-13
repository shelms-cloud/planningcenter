"""Compute every dashboard number from the tidy tables.

Writes
  out/metrics.json          aggregates only; safe to share
  out/private/at_risk.csv   names of people who have declined sharply (do not share)
  out/private/lapsed.csv    names of baseline regulars who have lapsed (do not share)

Every metric carries its numerator, denominator and definition so it can be
traced. Rows in data/tidy/activity.csv carry a `ref` back to the raw API page.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import numpy as np
import pandas as pd

import config as C

SMALL_N = 20  # breakout rows smaller than this are shown but flagged


def load():
    t = {}
    for name in ["people", "households", "events", "activity", "guests", "group_members",
                 "group_events", "headcounts", "campuses", "groups", "first_time"]:
        path = C.TIDY_DIR / f"{name}.csv"
        try:
            t[name] = pd.read_csv(path, dtype=str) if path.exists() else pd.DataFrame()
        except pd.errors.EmptyDataError:
            t[name] = pd.DataFrame()
    a = t["activity"]
    a["date"] = pd.to_datetime(a["date"]).dt.date
    ev_area = dict(zip(t["events"].get("event_id", []), t["events"].get("area", [])))
    a["area"] = np.where(a["source"] == "checkin", a["event_id"].map(ev_area), None)
    a.loc[(a["source"] == "checkin") & (a["kind"] == "volunteer"), "area"] = "serving"
    a = a[a["area"] != "ignore"]
    # Serving counts only when the person confirmed; unconfirmed requests are not activity.
    a = a[~((a["source"] == "serve") & (a["kind"] != "confirmed"))]
    a = a[(a["date"] >= C.HISTORY_START) & (a["date"] <= C.AS_OF)]
    t["activity"] = a
    p = t["people"]
    for col in ["created_at", "inactivated_at", "birthdate"]:
        p[col] = [x.date() if pd.notna(x) else None for x in pd.to_datetime(p[col], errors="coerce")]
    return t


def in_window(dates: pd.Series, w) -> pd.Series:
    return (dates >= w[0]) & (dates <= w[1])


def attendance(a: pd.DataFrame) -> pd.DataFrame:
    """Distinct person-days physically present: check-in (any kind), group
    attendance, or confirmed serving."""
    att = a[a["source"].isin(["checkin", "group", "serve"]) & (a["area"] != "special")]
    return att[["person_id", "date"]].drop_duplicates()


def days_in(att: pd.DataFrame, w) -> pd.Series:
    return att[in_window(att["date"], w)].groupby("person_id").size()


def regulars(att, w) -> set:
    d = days_in(att, w)
    return set(d[d >= C.REGULAR_MIN_DAYS].index)


def ever_regular_from(dates: np.ndarray) -> int | None:
    """Index of the first visit that starts a qualifying 91-day window, else None."""
    if len(dates) < C.REGULAR_MIN_DAYS:
        return None
    ends = np.searchsorted(dates, dates + C.REGULAR_WINDOW_DAYS - 1, side="right")
    hit = np.nonzero(ends - np.arange(len(dates)) >= C.REGULAR_MIN_DAYS)[0]
    return int(hit[0]) if len(hit) else None


def ordinal(d: dt.date) -> int:
    return d.toordinal()


def rate(num, den):
    return round(num / den, 4) if den else None


# ---------------------------------------------------------------------------


def person_profile(t, cohort: set, ref: dt.date, a: pd.DataFrame, att: pd.DataFrame) -> pd.DataFrame:
    """Attributes of each cohort member as of `ref` (end of baseline window)."""
    W = C.windows()
    p = t["people"].set_index("person_id")
    df = pd.DataFrame(index=sorted(cohort))
    df.index.name = "person_id"

    # Age band
    bd = p["birthdate"].reindex(df.index)
    age = bd.map(lambda b: (ref - b).days / 365.25 if isinstance(b, dt.date) else np.nan)
    df["age"] = age
    df["age_band"] = age.map(C.age_band)

    # Engagement in the 6 months ending at ref (groups are semester-based)
    six = (ref - dt.timedelta(days=181), ref)
    recent6 = a[in_window(a["date"], six)]
    grp = set(recent6.loc[recent6["source"] == "group", "person_id"])
    srv = set(recent6.loc[(recent6["source"] == "serve") |
                          ((recent6["source"] == "checkin") & (recent6["kind"] == "volunteer")),
                          "person_id"])
    gifts = a[(a["source"] == "give") & in_window(a["date"], W["baseline"])].copy()
    gifts["slice"] = gifts["date"].map(lambda d: min(2, (d - W["baseline"][0]).days // 31))
    giver = gifts.groupby("person_id")["slice"].nunique()
    reg_giver = set(giver[giver >= C.GIVING_MIN_MONTHS].index)
    df["in_group"] = df.index.isin(grp)
    df["serving"] = df.index.isin(srv)
    df["giving"] = df.index.isin(reg_giver)
    df["engagement"] = np.select(
        [df["in_group"] & df["serving"], df["in_group"], df["serving"]],
        ["Group + serving", "Group only", "Serving only"], "Neither")
    df["any_engaged"] = df["in_group"] | df["serving"] | df["giving"]

    # Household type
    hh = t["households"]
    if len(hh):
        sizes = hh.groupby("household_id").size()
        hh = hh.assign(size=hh["household_id"].map(sizes))
        main_hh = hh.sort_values("size", ascending=False).drop_duplicates("person_id")
        main_hh = main_hh.set_index("person_id")["household_id"]
        members = hh.merge(p[["child", "birthdate"]], left_on="person_id", right_index=True, how="left")
        members["is_child"] = (members["child"].astype(str).str.lower() == "true") | members["birthdate"].map(
            lambda b: isinstance(b, dt.date) and (ref - b).days < 18 * 365.25)
        comp = members.groupby("household_id").agg(kids=("is_child", "sum"), n=("person_id", "size"))
        comp["adults"] = comp["n"] - comp["kids"]
        # Households of 9+ are usually catch-all records, not one home.
        htype = np.select([comp["n"] >= 9, comp["kids"] > 0, comp["adults"] == 1, comp["adults"] == 2],
                          ["Large household record (9+)", "Family with kids", "Single adult",
                           "Couple (no kids at home)"], "3+ adults")
        htype = pd.Series(htype, index=comp.index)
        df["household_id"] = main_hh.reindex(df.index)
        df["household_type"] = df["household_id"].map(htype)
        # Planning Center usually has no household record for a single adult.
        df.loc[df["household_type"].isna() & (df["age"] >= 18), "household_type"] = "Single adult"
        df["household_type"] = df["household_type"].fillna("No household record")
    else:
        df["household_id"] = None
        df["household_type"] = "No household record"

    # Tenure at ref: earliest of People record creation and first activity
    first_act = a.groupby("person_id")["date"].min()
    created = p["created_at"].reindex(df.index)
    both = pd.concat([pd.to_datetime(created), pd.to_datetime(first_act.reindex(df.index))], axis=1)
    first_seen = both.min(axis=1)
    yrs = first_seen.map(lambda d: (pd.Timestamp(ref) - d).days / 365.25 if pd.notna(d) else np.nan)
    df["tenure"] = pd.cut(yrs, [-1, 1, 3, 1e9], labels=["Under 1 year", "1-3 years", "3+ years"]
                          ).astype(str).replace("nan", "Unknown")

    # Campus
    camp = dict(zip(t["campuses"].get("campus_id", []), t["campuses"].get("campus", [])))
    df["campus"] = p["campus_id"].reindex(df.index).map(camp).fillna("No campus set")

    # Ministry area and service time: most common in the baseline window
    base_ci = a[(a["source"] == "checkin") & in_window(a["date"], W["baseline"])]
    worship = base_ci[~base_ci["area"].isin(["serving"])]
    area = worship.groupby("person_id")["area"].agg(lambda s: s.mode().iat[0])
    by_age = df["age"].map(lambda x: "kids" if x < 11 else "students" if x < 18 else "cya"
                           if x < 30 else "adults" if x == x else "adults")
    df["ministry_area"] = area.reindex(df.index).fillna(by_age)
    df["ministry_source"] = np.where(df.index.isin(area.index), "check-in event", "age (fallback)")
    stime = base_ci.dropna(subset=["service_time"]).groupby("person_id")["service_time"].agg(
        lambda s: s.mode().iat[0])
    df["service_time"] = stime.reindex(df.index).fillna("No service time recorded")
    df["baseline_days"] = days_in(att, W["baseline"]).reindex(df.index).fillna(0).astype(int)
    df["status"] = p["status"].reindex(df.index)
    return df


def breakout(df: pd.DataFrame, col: str, order=None) -> list[dict]:
    g = df.groupby(col)
    rows = []
    for key, sub in g:
        n = len(sub)
        rows.append({"segment": str(key), "regulars": n, "lapsed": int(sub["lapsed"].sum()),
                     "lapse_rate": rate(sub["lapsed"].sum(), n),
                     "declined": int(sub["declined"].sum()),
                     "declined_rate": rate(sub["declined"].sum(), n),
                     "small_sample": n < SMALL_N})
    if order:
        rows.sort(key=lambda r: order.index(r["segment"]) if r["segment"] in order else 99)
    else:
        rows.sort(key=lambda r: -r["regulars"])
    return rows


def main():
    t = load()
    a, people = t["activity"], t["people"]
    W = C.windows()
    att = attendance(a)
    any_act = a[["person_id", "date"]].drop_duplicates()
    m: dict = {"as_of": C.AS_OF.isoformat(), "history_start": C.HISTORY_START.isoformat(),
               "windows": {k: [v[0].isoformat(), v[1].isoformat()] for k, v in W.items()},
               "definitions": {}}

    # ---- 1. Attrition ------------------------------------------------------
    base = regulars(att, W["baseline"])
    cur = regulars(att, W["current"])
    active_recent = set(any_act.loc[in_window(any_act["date"], W["recent_quiet"]), "person_id"])
    lapsed = base - active_recent
    retained = base & cur
    declined = (base & active_recent) - cur

    prof = person_profile(t, base, W["baseline"][1], a, att)
    prof["lapsed"] = prof.index.isin(lapsed)
    prof["declined"] = prof.index.isin(declined)
    inactive_lapsed = int(((prof["status"] == "inactive") & prof["lapsed"]).sum())

    m["attrition"] = {
        "baseline_regulars": len(base), "lapsed": len(lapsed), "rate": rate(len(lapsed), len(base)),
        "declined_not_lapsed": len(declined), "declined_rate": rate(len(declined), len(base)),
        "still_regular": len(retained), "still_regular_rate": rate(len(retained), len(base)),
        "lapsed_marked_inactive_in_pco": inactive_lapsed,
        "benchmark": list(C.HEALTHY_ATTRITION),
    }
    # Household-level sensitivity check: a household counts as lapsed only when
    # nobody in it has any activity in the last 90 days.
    hh = t["households"]
    if len(hh):
        base_hh = set(hh.loc[hh["person_id"].isin(base), "household_id"])
        active_hh = set(hh.loc[hh["person_id"].isin(active_recent), "household_id"])
        m["attrition"]["households"] = {"baseline": len(base_hh),
                                        "lapsed": len(base_hh - active_hh),
                                        "rate": rate(len(base_hh - active_hh), len(base_hh))}
    adults = prof[prof["age"] >= 18]
    m["attrition"]["adults_only"] = {"baseline": len(adults), "lapsed": int(adults["lapsed"].sum()),
                                     "rate": rate(adults["lapsed"].sum(), len(adults))}

    # ---- 2. Breakouts ------------------------------------------------------
    giving_available = bool((a["source"] == "give").any())
    m["giving_available"] = giving_available
    m["breakouts"] = {
        "engagement": breakout(prof, "engagement",
                               ["Group + serving", "Group only", "Serving only", "Neither"]),
        "giving": breakout(prof.assign(g=np.where(prof["giving"], "Regular giver", "Not a regular giver")), "g")
        if giving_available else [],
        "any_engaged": breakout(prof.assign(g=np.where(prof["any_engaged"], "Group, serving or giving" if giving_available
                                                         else "Group or serving", "Neither")), "g"),
        "age_band": breakout(prof, "age_band", [b[2] for b in C.AGE_BANDS] + ["Unknown"]),
        "household_type": breakout(prof, "household_type",
                                   ["Single adult", "Couple (no kids at home)", "Family with kids",
                                    "3+ adults", "No household record"]),
        "tenure": breakout(prof, "tenure", ["Under 1 year", "1-3 years", "3+ years", "Unknown"]),
        "campus": breakout(prof, "campus"),
        "service_time": breakout(prof, "service_time"),
        "ministry_area": breakout(prof, "ministry_area", ["kids", "students", "cya", "adults"]),
    }
    m["breakouts"]["ministry_area_fallback_share"] = rate(
        (prof["ministry_source"] == "age (fallback)").sum(), len(prof))

    # ---- 3. Newcomer funnel -------------------------------------------------
    first_any = any_act.groupby("person_id")["date"].min()
    first_att = att.groupby("person_id")["date"].min()
    created = people.set_index("person_id")["created_at"]
    grace = dt.timedelta(days=C.NEW_PERSON_GRACE_DAYS)
    connect = a[(a["source"].isin(["group", "serve"])) |
                ((a["source"] == "checkin") & (a["kind"] == "volunteer"))]
    first_connect = connect.groupby("person_id")["date"].min()
    att_sorted = att.sort_values("date")
    dates_by_p = {pid: np.array([ordinal(d) for d in g["date"]])
                  for pid, g in att_sorted.groupby("person_id")}

    ft = t["first_time"]
    flagged = set(zip(ft["person_id"], pd.to_datetime(ft["date"]).dt.date)) if len(ft) else set()

    def is_new(pid, first):
        # No earlier activity in the data, and either Planning Center flagged the
        # check-in as a first-time check-in or the People record is brand new.
        if first_any.get(pid) != first:
            return False
        c = created.get(pid)
        new_record = isinstance(c, dt.date) and c >= first - grace
        if C.NEWCOMER_RULE == "flag_or_record":
            return (pid, first) in flagged or new_record
        # Default: the People record must be new. Planning Center's own first-time flag
        # also fires for long-time attenders checked in for the first time (adult check-in
        # coverage roughly doubled in Feb 2026), so it is only used when no record date exists.
        return new_record or (not isinstance(c, dt.date) and (pid, first) in flagged)

    newc = []
    for pid, first in first_att.items():
        if not (C.HISTORY_START + dt.timedelta(days=C.NEWCOMER_LOOKBACK_DAYS) <= first <= C.AS_OF):
            continue  # need some prior history to call someone "new"
        if not is_new(pid, first):
            continue
        d = dates_by_p[pid]
        reg_idx = ever_regular_from(d)
        fc = first_connect.get(pid)
        newc.append({"person_id": pid, "first": first, "visits": len(d),
                     "regular": reg_idx is not None,
                     "regular_on": dt.date.fromordinal(int(d[reg_idx])) if reg_idx is not None else None,
                     "connected": isinstance(fc, dt.date) and fc >= first,
                     "active_recent": pid in active_recent,
                     "regular_now": pid in cur})
    newc = pd.DataFrame(newc, columns=["person_id", "first", "visits", "regular", "regular_on",
                                       "connected", "active_recent", "regular_now"])
    nw = newc[in_window(newc["first"], W["newcomer"])] if len(newc) else newc
    mature_cut = C.AS_OF - dt.timedelta(days=120)
    mature = nw[nw["first"] <= mature_cut]

    def funnel(df):
        return [
            {"stage": "First visit", "n": len(df)},
            {"stage": "Second visit", "n": int((df["visits"] >= 2).sum())},
            {"stage": "Third visit", "n": int((df["visits"] >= 3).sum())},
            {"stage": "Regular attender", "n": int(df["regular"].sum())},
            {"stage": "Connected to a group or team", "n": int((df["regular"] & df["connected"]).sum())},
        ]

    guests = t["guests"]
    if len(guests):
        guests["date"] = pd.to_datetime(guests["date"]).dt.date
    m["newcomers"] = {
        "funnel_all": funnel(nw), "funnel_mature": funnel(mature),
        "mature_cutoff": mature_cut.isoformat(),
        "retention_rate": rate(mature["regular"].sum(), len(mature)),
        "retention_numerator": int(mature["regular"].sum()), "retention_denominator": len(mature),
        "connected_any": int(nw["connected"].sum()),
        "one_time_guest_checkins": int(in_window(guests["date"], W["newcomer"]).sum()) if len(guests) else 0,
        "by_month": [],
    }
    if len(nw):
        nw = nw.assign(month=nw["first"].map(lambda d: d.strftime("%Y-%m")))
        for mo, g in nw.groupby("month"):
            m["newcomers"]["by_month"].append({
                "month": mo, "first_visits": len(g), "second": int((g["visits"] >= 2).sum()),
                "regular": int(g["regular"].sum()),
                "mature": bool(g["first"].max() <= mature_cut)})

    # ---- 4. Net growth ----------------------------------------------------
    retained_new = nw[nw["regular"] & nw["active_recent"]] if len(nw) else nw
    newc_ids = set(nw["person_id"]) if len(nw) else set()
    returning = cur - base - newc_ids
    m["net_growth"] = {
        "retained_newcomers": len(retained_new), "lapsed": len(lapsed),
        "net": len(retained_new) - len(lapsed),
        "regulars_then": len(base), "regulars_now": len(cur),
        "regulars_change": len(cur) - len(base),
        "regulars_change_rate": rate(len(cur) - len(base), len(base)),
        "now_composition": {"still regular from a year ago": len(retained),
                            "newcomers who became regular": len(cur & newc_ids),
                            "returning / previously irregular": len(returning)},
    }

    # Sunday headcount / check-in trend by month (what the room "looks like")
    hc = t["headcounts"]
    trend = {}
    if len(hc):
        hc["date"] = pd.to_datetime(hc["date"]).dt.date
        hc["headcount"] = pd.to_numeric(hc["headcount"], errors="coerce").fillna(0)
        hc = hc[hc["date"] >= C.HISTORY_START]
        hc["month"] = hc["date"].map(lambda d: d.strftime("%Y-%m"))
        hc["dow"] = hc["date"].map(lambda d: d.weekday())
        sun = hc[hc["dow"] == 6].groupby(["month", "date"])["headcount"].sum().groupby("month").mean()
        trend["sunday_headcount_avg"] = {k: round(v) for k, v in sun.items() if v > 0}
    ci = a[(a["source"] == "checkin") & ~a["area"].isin(["serving", "special"]) &
           (pd.Series([d.weekday() for d in a["date"]], index=a.index) == 6)]
    ci = ci.assign(month=ci["date"].map(lambda d: d.strftime("%Y-%m")))
    trend["sunday_checkins_avg"] = {k: round(v) for k, v in
                                    ci.groupby(["month", "date"]).size().groupby("month").mean().items()}
    names = dict(zip(t["events"].get("event_id", []), t["events"].get("name", [])))
    by_ev = {}
    for nm in ["Sunday Experience", "Sunday Kids Check-In", "Sunday Dream Team Check-In"]:
        sub = a[(a["source"] == "checkin") & (a["event_id"].map(names) == nm)]
        sub = sub[[d.weekday() == 6 for d in sub["date"]]]
        if len(sub):
            sub = sub.assign(month=sub["date"].map(lambda d: d.strftime("%Y-%m")))
            by_ev[nm] = {k: round(v) for k, v in sub.groupby(["month", "date"])["person_id"].nunique()
                         .groupby("month").mean().items()}
    trend["sunday_checkins_by_event"] = by_ev
    reg_by_q = {}
    for months_back in range(0, 25, 3):
        end = C.AS_OF - dt.timedelta(days=round(months_back * 30.44))
        w = (end - dt.timedelta(days=C.REGULAR_WINDOW_DAYS - 1), end)
        if w[0] < C.HISTORY_START:
            break
        reg_by_q[end.isoformat()] = len(regulars(att, w))
    trend["regulars_rolling"] = dict(sorted(reg_by_q.items()))
    m["net_growth"]["trend"] = trend
    # Regulars then vs now by age group: kids' check-in recording was steady all year,
    # adults' was not (Sunday Experience coverage roughly doubled from Feb 2026).
    bd = people.set_index("person_id")["birthdate"]

    def grp(pid, ref):
        b = bd.get(pid)
        if not isinstance(b, dt.date):
            return "Age unknown"
        age = (ref - b).days / 365.25
        return "Kids (0-10)" if age < 11 else "Students (11-17)" if age < 18 else "Adults (18+)"
    by = {}
    for label, ids, ref in [("then", base, W["baseline"][1]), ("now", cur, C.AS_OF)]:
        for pid in ids:
            g = grp(pid, ref)
            by.setdefault(g, {"then": 0, "now": 0})[label] += 1
    m["net_growth"]["regulars_by_age"] = by
    # Alternative newcomer rule, so the range is visible
    alt = 0
    for pid, first in first_att.items():
        if (C.HISTORY_START + dt.timedelta(days=C.NEWCOMER_LOOKBACK_DAYS) <= first <= C.AS_OF
                and in_window(pd.Series([first]), W["newcomer"]).iat[0] and first_any.get(pid) == first
                and ((pid, first) in flagged or (isinstance(created.get(pid), dt.date) and created.get(pid) >= first - grace))
                and ever_regular_from(dates_by_p[pid]) is not None and pid in active_recent):
            alt += 1
    m["net_growth"]["retained_newcomers_loose_rule"] = alt
    m["net_growth"]["net_loose_rule"] = alt - len(lapsed)

    # ---- 5. Seasonality --------------------------------------------------
    last_any = any_act.groupby("person_id")["date"].max()
    last_att = att.groupby("person_id")["date"].max()
    ever_reg = {pid for pid, d in dates_by_p.items() if ever_regular_from(d) is not None}
    quiet_cut = C.AS_OF - dt.timedelta(days=C.LAPSE_QUIET_DAYS)
    lost = [last_att[p] for p in ever_reg if last_any[p] < quiet_cut]
    lost_m = pd.Series([d.strftime("%Y-%m") for d in lost]).value_counts()
    gained_m = (newc.assign(m=newc["first"].map(lambda d: d.strftime("%Y-%m")))
                .groupby("m").size() if len(newc) else pd.Series(dtype=int))
    reg_gained = (newc[newc["regular"]].assign(m=newc["regular_on"].map(
        lambda d: d.strftime("%Y-%m") if isinstance(d, dt.date) else None)).groupby("m").size()
        if len(newc) else pd.Series(dtype=int))
    start_m = (C.HISTORY_START + dt.timedelta(days=C.NEWCOMER_LOOKBACK_DAYS)).strftime("%Y-%m")
    months = pd.period_range(start_m, C.AS_OF.strftime("%Y-%m"), freq="M").strftime("%Y-%m")
    m["seasonality"] = [{
        "month": mo,
        "lost": int(lost_m.get(mo, 0)) if mo < quiet_cut.strftime("%Y-%m") else None,
        "first_visits": int(gained_m.get(mo, 0)) if mo >= (C.HISTORY_START + dt.timedelta(
            days=C.NEWCOMER_LOOKBACK_DAYS)).strftime("%Y-%m") else None,
        "became_regular": int(reg_gained.get(mo, 0)) if mo >= start_m else None,
    } for mo in months]
    m["seasonality_note"] = (f"'Lost' = ever-regular people whose last attendance fell in that month and "
                             f"who have had no activity of any kind for {C.LAPSE_QUIET_DAYS}+ days. Months "
                             f"from {quiet_cut.strftime('%b %Y')} on are not yet knowable.")

    # ---- 6. Early warning --------------------------------------------------
    m["early_warning"] = early_warning(a, att, base, lapsed, last_att)

    # ---- 7. At-risk (private) ---------------------------------------------
    at_risk = build_at_risk(t, a, att, lapsed, active_recent)
    C.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    at_risk.to_csv(C.PRIVATE_DIR / "at_risk.csv", index=False)
    lap = prof[prof["lapsed"]].join(people.set_index("person_id")[["first_name", "last_name", "membership"]])
    lap["last_attended"] = last_att.reindex(lap.index)
    lap["last_any_activity"] = last_any.reindex(lap.index)
    lap["pco_link"] = [f"https://people.planningcenteronline.com/people/AC{i}" for i in lap.index]
    lap[["first_name", "last_name", "age_band", "household_type", "ministry_area", "engagement",
         "giving", "last_attended", "last_any_activity", "status", "membership", "pco_link"]
        ].sort_values("last_attended", ascending=False).to_csv(C.PRIVATE_DIR / "lapsed.csv")
    # Still around but no longer regular: what kept each person in touch recently.
    rec = a[in_window(a["date"], W["recent_quiet"]) & a["person_id"].isin(declined)]
    label = np.select([rec["source"] == "group",
                       (rec["source"] == "serve") | (rec["area"] == "serving"),
                       rec["area"] == "special"],
                      ["group", "serving", "event/conference"], "Sunday/ministry check-in")
    doing = pd.Series(label, index=rec.index).groupby(rec["person_id"]).agg(lambda x: "; ".join(sorted(set(x))))
    dec = prof[prof["declined"]].join(people.set_index("person_id")[["first_name", "last_name", "membership"]])
    dec["last90_days"] = days_in(att, W["recent_quiet"]).reindex(dec.index).fillna(0).astype(int)
    dec["still_doing"] = doing.reindex(dec.index).fillna("")
    dec["last_attended"] = last_att.reindex(dec.index)
    dec["pco_link"] = [f"https://people.planningcenteronline.com/people/AC{i}" for i in dec.index]
    dec.sort_values(["last90_days", "baseline_days"], ascending=[True, False])[
        ["first_name", "last_name", "age_band", "household_type", "ministry_area", "engagement",
         "baseline_days", "last90_days", "still_doing", "last_attended", "membership", "pco_link"]
    ].to_csv(C.PRIVATE_DIR / "declined.csv")
    m["at_risk_count"] = len(at_risk)

    # ---- Data gaps -------------------------------------------------------
    m["data_gaps"] = data_gaps(t, a, att, prof, base)

    C.OUT_DIR.mkdir(parents=True, exist_ok=True)
    (C.OUT_DIR / "metrics.json").write_text(json.dumps(m, indent=1, default=str))
    print(json.dumps({k: m[k] for k in ["attrition", "net_growth"]}, indent=1, default=str)[:3000])


def early_warning(a, att, base, lapsed, last_att) -> dict:
    """Compare what lapsers looked like before their last visit with people who
    stayed, measured over the same calendar dates.

    Each signal compares a 91-day window with the person's own baseline window
    (the 91 days in which they qualified as a regular). Windows that would start
    before the baseline ends are skipped, so the two never overlap."""
    W = C.windows()
    b0, b1 = (ordinal(d) for d in W["baseline"])
    six0 = b1 - 181
    lap_ref = {p: last_att[p] for p in sorted(lapsed) if p in last_att.index}
    if not lap_ref:
        return {"lapsed_n": 0}
    # People who stayed are evaluated at every lapsed person's reference date and
    # averaged, so the comparison covers the same calendar dates with no random draw.
    ref_weights = pd.Series(list(lap_ref.values())).value_counts()
    stayed = sorted(base - lapsed)

    vol = a[(a["source"] == "checkin") & (a["kind"] == "volunteer")]
    sets = {"att": att, "group": a[a["source"] == "group"],
            "serve": pd.concat([a[a["source"] == "serve"], vol]), "give": a[a["source"] == "give"]}
    idx = {k: {p: np.array(sorted({ordinal(d) for d in g["date"]}))
               for p, g in v.groupby("person_id")} for k, v in sets.items()}

    def count(kind, pid, lo, hi):
        d = idx[kind].get(pid)
        if d is None:
            return 0
        return int(np.searchsorted(d, hi, "right") - np.searchsorted(d, lo, "left"))

    has_give = bool(len(sets["give"]))
    periods = {"6-3 months before": (182, 92), "3-0 months before": (91, 1)}

    def signals(pid, ref):
        r = ordinal(ref)
        base_att = count("att", pid, b0, b1)
        grp = count("group", pid, six0, b1) > 0
        srv = count("serve", pid, six0, b1) > 0
        giv = count("give", pid, b0, b1) >= 2
        out = {}
        for label, (lo, hi) in periods.items():
            w = (r - lo, r - hi)
            if w[0] <= b1:
                out[label] = None  # window overlaps the baseline: not measurable
                continue
            sig = {
                "Attendance fell by half or more": count("att", pid, *w) <= base_att / 2,
                "Stopped attending their group": grp and count("group", pid, *w) == 0,
                "Stopped serving": srv and count("serve", pid, *w) == 0,
            }
            if has_give:
                sig["Stopped giving"] = giv and count("give", pid, *w) == 0
            out[label] = sig
        curve = []
        for k in range(-9, 0):
            lo = r + round(k * 30.44)
            curve.append(count("att", pid, lo, lo + 29) if lo >= ordinal(C.HISTORY_START) else None)
        return out, curve

    total_w = float(ref_weights.sum())
    lap_rows, lap_curves = [], []
    for pid, ref in lap_ref.items():
        s_, curve = signals(pid, ref)
        lap_rows.append(s_)
        lap_curves.append(curve)
    # stayed: per period, effective n and effective hits (weighted over reference dates)
    st_n = {p: 0.0 for p in periods}
    st_hits = {p: {} for p in periods}
    st_curve_sum, st_curve_n = np.zeros(9), np.zeros(9)
    for pid in stayed:
        for ref, w in ref_weights.items():
            s_, curve = signals(pid, ref)
            wt = w / total_w
            for p in periods:
                if s_[p] is None:
                    continue
                st_n[p] += wt
                for sig, hit in s_[p].items():
                    st_hits[p][sig] = st_hits[p].get(sig, 0.0) + wt * hit
            for i, c in enumerate(curve):
                if c is not None:
                    st_curve_sum[i] += wt * c
                    st_curve_n[i] += wt

    out = {"lapsed_n": len(lap_rows), "stayed_n": len(stayed), "signals": []}
    for period in periods:
        lap = [r[period] for r in lap_rows if r[period] is not None]
        if not lap or st_n[period] < 1:
            continue
        for sig in lap[0]:
            lh = sum(r[sig] for r in lap)
            sh = st_hits[period].get(sig, 0.0)
            n_l, n_s = len(lap), st_n[period]
            p_with = lh / (lh + sh) if lh + sh else None
            p_without = (n_l - lh) / (n_l + n_s - lh - sh) if (n_l + n_s - lh - sh) else None
            out["signals"].append({
                "period": period, "signal": sig, "lapsed_n": n_l, "stayed_n": round(n_s),
                "lapsed_pct": rate(lh, n_l), "stayed_pct": round(sh / n_s, 4),
                "lapse_rate_with_signal": round(p_with, 4) if p_with is not None else None,
                "lapse_rate_without": round(p_without, 4) if p_without is not None else None,
                "relative_risk": round(p_with / p_without, 2) if p_with and p_without else None,
            })
    curves = {"lapsed": lap_curves}

    def mean(vals):
        v = [x for x in vals if x is not None]
        return round(float(np.mean(v)), 2) if len(v) >= 10 else None
    out["curve"] = {"lapsed": [mean([c[i] for c in lap_curves]) for i in range(9)],
                    "stayed": [round(float(st_curve_sum[i] / st_curve_n[i]), 2) if st_curve_n[i] else None
                               for i in range(9)]}
    out["curve_months"] = list(range(-9, 0))
    out["baseline_days_avg"] = {
        "lapsed": round(float(np.mean([count("att", p, b0, b1) for p in lap_ref])), 2),
        "stayed": round(float(np.mean([count("att", p, b0, b1) for p in stayed])), 2) if stayed else None}
    return out


def build_at_risk(t, a, att, lapsed, active_recent) -> pd.DataFrame:
    W = C.windows()
    prior_days = days_in(att, W["at_risk_prior"])
    recent_days = days_in(att, W["at_risk_recent"])
    scale = C.AT_RISK_RECENT_DAYS / C.REGULAR_WINDOW_DAYS
    was_reg = prior_days[prior_days >= C.REGULAR_MIN_DAYS]
    rec = recent_days.reindex(was_reg.index).fillna(0)
    expected = was_reg * scale
    drop = 1 - rec / expected
    flagged = drop[drop >= C.AT_RISK_DROP].index
    p = t["people"].set_index("person_id")
    flagged = [x for x in flagged if p["status"].get(x) != "inactive"]

    def recent_src(src, pid, w):
        g = a[(a["person_id"] == pid) & (a["source"] == src)]
        return in_window(g["date"], w).any()

    last_att = att.groupby("person_id")["date"].max()
    rows = []
    for pid in flagged:
        prior_w, rec_w = W["at_risk_prior"], W["at_risk_recent"]
        signals = []
        for src, label in [("group", "left group"), ("serve", "stopped serving"), ("give", "stopped giving")]:
            if recent_src(src, pid, prior_w) and not recent_src(src, pid, rec_w):
                signals.append(label)
        if pid not in active_recent:
            signals.append("no activity of any kind in 90 days")
        last = last_att.get(pid)
        rows.append({
            "person_id": pid,
            "first_name": p["first_name"].get(pid), "last_name": p["last_name"].get(pid),
            "membership": p["membership"].get(pid),
            "prior_90d_attendances": int(was_reg[pid]),
            "last_90d_attendances": int(rec[pid]),
            "drop_pct": round(float(drop[pid]) * 100),
            "last_attended": last,
            "days_since": (C.AS_OF - last).days if isinstance(last, dt.date) else None,
            "other_signals": "; ".join(signals),
            "pco_link": f"https://people.planningcenteronline.com/people/AC{pid}",
        })
    df = pd.DataFrame(rows, columns=["person_id", "first_name", "last_name", "membership",
                                     "prior_90d_attendances", "last_90d_attendances", "drop_pct",
                                     "last_attended", "days_since", "other_signals", "pco_link"])
    if len(df):
        bd = p["birthdate"]
        df["age"] = df["person_id"].map(lambda x: int((C.AS_OF - bd.get(x)).days // 365.25)
                                        if isinstance(bd.get(x), dt.date) else None)
        hh = t["households"]
        if len(hh):
            first_hh = hh.drop_duplicates("person_id").set_index("person_id")["household_id"]
            df["household_id"] = df["person_id"].map(first_hh)
        df = df.sort_values(["drop_pct", "prior_90d_attendances"], ascending=[False, False])
    return df


def data_gaps(t, a, att, prof, base) -> dict:
    p = t["people"]
    active = p[p["status"] == "active"]
    seen = set(a["person_id"])
    W = C.windows()
    out = {
        "people_records_used": len(p),
        "active_people_in_pco": int(os.environ.get("ACTIVE_PEOPLE_TOTAL", len(active))),
        "people_with_any_activity": len(seen),
        "missing_birthdate_pct_of_regulars": rate(prof["age"].isna().sum(), len(prof)),
        "no_household_pct_of_regulars": rate((prof["household_type"] == "No household record").sum(), len(prof)),
        "no_service_time_pct_of_regulars": rate((prof["service_time"] == "No service time recorded").sum(), len(prof)),
        "campuses": int(t["campuses"]["campus_id"].nunique()) if len(t["campuses"]) else 0,
        "activity_rows_by_source": a.groupby("source").size().to_dict(),
    }
    ge = t["group_events"]
    if len(ge):
        ge["date"] = pd.to_datetime(ge["date"]).dt.date
        ge = ge[(ge["canceled"].astype(str).str.lower() != "true") & in_window(ge["date"], (C.HISTORY_START, C.AS_OF))]
        out["group_meetings"] = len(ge)
        out["group_meetings_without_attendance_pct"] = rate((ge["attendees"].astype(int) == 0).sum(), len(ge))
        gm = t["group_members"]
        per_group = ge.assign(att=ge["attendees"].astype(int)).groupby("group_id")["att"].sum()
        out["groups_meeting"] = int(len(per_group))
        out["groups_never_recording_attendance"] = int((per_group == 0).sum())
        if len(gm):
            out["current_group_members"] = int(gm["person_id"].nunique())
            in_att = set(a.loc[(a["source"] == "group") & in_window(a["date"], W["current"]), "person_id"])
            out["current_members_with_no_recorded_group_attendance_90d"] = int(
                (~gm["person_id"].drop_duplicates().isin(in_att)).sum())
    dup = p.dropna(subset=["birthdate"]).groupby(
        [p["first_name"].str.lower(), p["last_name"].str.lower(), "birthdate"]).size()
    out["possible_duplicate_people"] = int((dup[dup > 1] - 1).sum())
    ev = t["events"]
    if len(ev):
        used = a[a["source"] == "checkin"].groupby("event_id").size()
        ev = ev.assign(checkins=ev["event_id"].map(used).fillna(0).astype(int))
        out["event_area_map"] = ev[ev["checkins"] > 0].sort_values("checkins", ascending=False)[
            ["name", "area", "checkins"]].to_dict("records")
    # Adults vs kids: how much of the baseline cohort is children (who must check in)
    out["baseline_regulars_under_18_pct"] = rate((prof["age"] < 18).sum(), len(prof))
    # How each baseline regular shows up in the data: Sunday check-ins alone, or
    # only through groups/serving (people the Sunday count would miss).
    base_att = a[a["person_id"].isin(base) & in_window(a["date"], W["baseline"])]
    srcs = base_att[base_att["source"] != "give"].groupby("person_id")["source"].agg(set)
    out["baseline_regulars_seen_via"] = {
        "check-ins only": int(srcs.map(lambda s: s == {"checkin"}).sum()),
        "check-ins plus group/serving": int(srcs.map(lambda s: "checkin" in s and len(s) > 1).sum()),
        "group/serving only, never checked in": int(srcs.map(lambda s: "checkin" not in s).sum()),
    }
    return out


if __name__ == "__main__":
    main()
