"""Flatten the raw API pages in data/raw into tidy CSV tables in data/tidy.

Tables
  people.csv        one row per person
  households.csv    household_id, person_id (a person can be in several)
  events.csv        Check-Ins events with the ministry area each maps to
  activity.csv      one row per person per activity: check-in, group attendance,
                    serving (scheduled and not declined), or gift
  guests.csv        one-time-guest check-ins (no person record) per date
  group_members.csv current group memberships
  group_events.csv  every group meeting and whether attendance was taken
  headcounts.csv    headcount totals per event time
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from config import RAW_DIR, TIDY_DIR, TZ, event_area

LOCAL = ZoneInfo(TZ)


def pages(name: str):
    base = RAW_DIR / name
    if not base.exists():
        return
    for f in sorted(base.rglob("*.json")):
        yield f.relative_to(RAW_DIR), json.loads(f.read_text())


def local_dt(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(LOCAL)


def local_date(ts: str | None) -> str | None:
    d = local_dt(ts)
    return d.date().isoformat() if d else None


def rel_id(obj: dict, name: str) -> str | None:
    data = (obj.get("relationships", {}).get(name) or {}).get("data")
    if isinstance(data, list):
        return data[0]["id"] if data else None
    return data["id"] if data else None


def build_people():
    rows = []
    for _, page in pages("people"):
        for p in page["data"]:
            a = p["attributes"]
            rows.append({
                "person_id": p["id"],
                "first_name": a.get("nickname") or a.get("given_name") or a.get("first_name"),
                "last_name": a.get("last_name"),
                "birthdate": a.get("birthdate"),
                "child": a.get("child"),
                "grade": a.get("grade"),
                "gender": a.get("gender"),
                "membership": a.get("membership"),
                "status": a.get("status"),
                "created_at": local_date(a.get("created_at")),
                "inactivated_at": local_date(a.get("inactivated_at")),
                "campus_id": rel_id(p, "primary_campus"),
            })
    pd.DataFrame(rows).drop_duplicates("person_id").to_csv(TIDY_DIR / "people.csv", index=False)

    hh = []
    for _, page in pages("households"):
        for h in page["data"]:
            for m in (h.get("relationships", {}).get("people", {}) or {}).get("data", []):
                hh.append({"household_id": h["id"], "person_id": m["id"],
                           "primary_contact_id": h["attributes"].get("primary_contact_id")})
    pd.DataFrame(hh, columns=["household_id", "person_id", "primary_contact_id"]).to_csv(
        TIDY_DIR / "households.csv", index=False)

    camp = [{"campus_id": c["id"], "campus": c["attributes"].get("name")}
            for _, page in pages("campuses") for c in page["data"]]
    pd.DataFrame(camp, columns=["campus_id", "campus"]).to_csv(TIDY_DIR / "campuses.csv", index=False)


def build_checkins(activity: list, guests: list):
    events = {}
    for _, page in pages("checkin_events"):
        for e in page["data"]:
            events[e["id"]] = e["attributes"].get("name")
    for src, page in pages("checkins"):
        inc = {(i["type"], i["id"]): i["attributes"] for i in page.get("included", [])}
        for c in page["data"]:
            a = c["attributes"]
            ev = rel_id(c, "event")
            if ev and ev not in events:
                events[ev] = (inc.get(("Event", ev)) or {}).get("name")
            period = inc.get(("EventPeriod", rel_id(c, "event_period") or "")) or {}
            etime = inc.get(("EventTime", rel_id(c, "event_times") or "")) or {}
            when = local_dt(etime.get("starts_at") or period.get("starts_at") or a.get("created_at"))
            date = when.date().isoformat()
            stime = local_dt(etime.get("starts_at"))
            pid = rel_id(c, "person")
            if a.get("one_time_guest") or not pid:
                guests.append({"date": date, "event_id": ev})
                continue
            activity.append({
                "person_id": pid, "date": date, "source": "checkin",
                "kind": (a.get("kind") or "").lower(), "event_id": ev,
                "service_time": stime.strftime("%a %-I:%M %p") if stime else None,
                "ref": f"{src}#{c['id']}",
            })
    ev = pd.DataFrame([{"event_id": k, "name": v, "area": event_area(v)} for k, v in events.items()],
                      columns=["event_id", "name", "area"])
    ev.to_csv(TIDY_DIR / "events.csv", index=False)

    hc = []
    for src, page in pages("event_times"):
        inc = {(i["type"], i["id"]): i["attributes"] for i in page.get("included", [])}
        for t in page["data"]:
            date = local_date(t["attributes"].get("starts_at"))
            ev_id = rel_id(t, "event")
            total = 0
            for h in (t.get("relationships", {}).get("headcounts", {}) or {}).get("data", []):
                total += (inc.get(("Headcount", h["id"])) or {}).get("total") or 0
            hc.append({"date": date, "event_id": ev_id, "event_name": events.get(ev_id),
                       "headcount": total, "regular_count": t["attributes"].get("regular_count"),
                       "guest_count": t["attributes"].get("guest_count"),
                       "volunteer_count": t["attributes"].get("volunteer_count")})
    pd.DataFrame(hc, columns=["date", "event_id", "event_name", "headcount", "regular_count",
                              "guest_count", "volunteer_count"]).to_csv(
        TIDY_DIR / "headcounts.csv", index=False)


def build_groups(activity: list):
    groups = {}
    for _, page in pages("groups"):
        inc = {(i["type"], i["id"]): i["attributes"] for i in page.get("included", [])}
        for g in page["data"]:
            gt = rel_id(g, "group_type")
            groups[g["id"]] = {"name": g["attributes"].get("name"),
                               "group_type": (inc.get(("GroupType", gt or "")) or {}).get("name")}
    members = []
    for src, page in pages("group_members"):
        gid = src.parts[1]
        for m in page["data"]:
            members.append({"group_id": gid, "person_id": rel_id(m, "person"),
                            "role": m["attributes"].get("role"),
                            "joined_at": local_date(m["attributes"].get("joined_at")),
                            "group_type": groups.get(gid, {}).get("group_type")})
    pd.DataFrame(members, columns=["group_id", "person_id", "role", "joined_at", "group_type"]).to_csv(
        TIDY_DIR / "group_members.csv", index=False)

    ev_rows, ev_date = [], {}
    for src, page in pages("group_events"):
        gid = src.parts[1]
        for e in page["data"]:
            a = e["attributes"]
            ev_date[e["id"]] = (gid, local_date(a.get("starts_at")))
            ev_rows.append({"group_event_id": e["id"], "group_id": gid,
                            "date": local_date(a.get("starts_at")),
                            "canceled": bool(a.get("canceled"))})
    taken = defaultdict(int)
    for src, page in pages("group_attendance"):
        eid = src.parts[1]
        gid, date = ev_date.get(eid, (None, None))
        for att in page["data"]:
            if not att["attributes"].get("attended"):
                continue
            taken[eid] += 1
            activity.append({"person_id": rel_id(att, "person"), "date": date, "source": "group",
                             "kind": att["attributes"].get("role"), "event_id": gid,
                             "service_time": None, "ref": f"{src}#{att['id']}"})
    ge = pd.DataFrame(ev_rows, columns=["group_event_id", "group_id", "date", "canceled"])
    ge["attendees"] = ge["group_event_id"].map(taken).fillna(0).astype(int)
    ge.to_csv(TIDY_DIR / "group_events.csv", index=False)
    pd.DataFrame([{"group_id": k, **v} for k, v in groups.items()],
                 columns=["group_id", "name", "group_type"]).to_csv(TIDY_DIR / "groups.csv", index=False)


def build_services(activity: list):
    plan_date = {}
    for src, page in pages("plans"):
        for p in page["data"]:
            plan_date[p["id"]] = local_date(p["attributes"].get("sort_date"))
    for src, page in pages("plan_people"):
        plan_id = src.parts[2]
        inc = {(i["type"], i["id"]): i["attributes"] for i in page.get("included", [])}
        for pp in page["data"]:
            status = (pp["attributes"].get("status") or "").upper()
            pid = rel_id(pp, "person")
            if status.startswith("D") or not pid:  # declined: not serving
                continue
            team = (inc.get(("Team", rel_id(pp, "team") or "")) or {}).get("name")
            activity.append({"person_id": pid, "date": plan_date.get(plan_id), "source": "serve",
                             "kind": "confirmed" if status.startswith("C") else "unconfirmed",
                             "event_id": team, "service_time": None, "ref": f"{src}#{pp['id']}"})


def build_giving(activity: list):
    for src, page in pages("donations"):
        for d in page["data"]:
            a = d["attributes"]
            pid = rel_id(d, "person")
            if a.get("refunded") or (a.get("payment_status") or "succeeded") != "succeeded" or not pid:
                continue
            activity.append({"person_id": pid, "date": local_date(a.get("received_at")),
                             "source": "give", "kind": None, "event_id": None,
                             "service_time": None, "ref": f"{src}#{d['id']}"})


def main():
    TIDY_DIR.mkdir(parents=True, exist_ok=True)
    build_people()
    activity, guests = [], []
    build_checkins(activity, guests)
    build_groups(activity)
    build_services(activity)
    build_giving(activity)
    act = pd.DataFrame(activity, columns=["person_id", "date", "source", "kind", "event_id",
                                          "service_time", "ref"]).dropna(subset=["person_id", "date"])
    act.to_csv(TIDY_DIR / "activity.csv", index=False)
    pd.DataFrame(guests, columns=["date", "event_id"]).to_csv(TIDY_DIR / "guests.csv", index=False)
    print(act.groupby("source").size().to_string())


if __name__ == "__main__":
    main()
