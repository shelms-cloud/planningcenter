"""Generate a SYNTHETIC Planning Center dataset in raw API page format.

Test-only: exercises build.py / analyze.py / render.py end to end without
touching real data. Nothing generated here is real or should be presented.

Usage: ATTRITION_DATA=/tmp/fx python3 tests/make_fixture.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import AS_OF, RAW_DIR  # noqa: E402

rnd = random.Random(42)
START = dt.date(2023, 1, 1)
SUNDAYS = [START + dt.timedelta(days=(6 - START.weekday()) % 7 + 7 * i) for i in range(200)]
SUNDAYS = [d for d in SUNDAYS if d <= AS_OF]
EVENTS = {"1": "Sunday Experience", "2": "Sunday Kids Check-In", "3": "Sunday Dream Team Check-In",
          "4": "Motion Night", "5": "CY Night", "6": "Check-In Test"}


def ts(d: dt.date, hour=15):
    return f"{d.isoformat()}T{hour:02d}:00:00Z"


def write(name, records, included=None):
    out = RAW_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    for i in range(0, max(1, len(records)), 100):
        (out / f"{i // 100:05d}.json").write_text(json.dumps(
            {"data": records[i:i + 100], "included": included or [], "links": {}}))
    (out / "_complete").write_text("1")


def rel(t, i):
    return {"data": {"type": t, "id": str(i)} if i is not None else None}


people, households, checkins, donations = [], [], [], []
group_att, plan_people = {}, []
pid = 1000
hid = 1
for _ in range(260):  # households
    kind = rnd.choice(["single", "couple", "family", "family"])
    first_year = rnd.choice([2016, 2019, 2022, 2023, 2024, 2025, 2026])
    created = dt.date(first_year, rnd.randint(1, 12), rnd.randint(1, 28))
    if created > AS_OF:
        created = AS_OF - dt.timedelta(days=rnd.randint(10, 200))
    members = []
    n_adults = 1 if kind == "single" else 2
    n_kids = rnd.randint(1, 3) if kind == "family" else 0
    for k in range(n_adults + n_kids):
        pid += 1
        child = k >= n_adults
        age = rnd.randint(1, 17) if child else rnd.randint(19, 80)
        bd = dt.date(AS_OF.year - age, rnd.randint(1, 12), 15)
        people.append({"type": "Person", "id": str(pid), "attributes": {
            "first_name": f"P{pid}", "last_name": f"H{hid}", "birthdate": bd.isoformat() if rnd.random() > .08 else None,
            "child": child, "membership": rnd.choice(["Member", "Regular Attender", "Visitor"]),
            "status": "active", "created_at": ts(created), "inactivated_at": None},
            "relationships": {"primary_campus": rel("Campus", 1)}})
        members.append((pid, child, age))
    households.append({"type": "Household", "id": str(hid), "attributes": {"primary_contact_id": str(members[0][0])},
                       "relationships": {"people": {"data": [{"type": "Person", "id": str(m[0])} for m in members]}}})
    hid += 1
    # Household behaviour
    start = max(created, START)
    p_attend = rnd.choice([0.15, 0.5, 0.7, 0.85])
    lapse_on = AS_OF - dt.timedelta(days=rnd.randint(100, 400)) if rnd.random() < 0.25 else None
    in_group = rnd.random() < 0.35
    serves = rnd.random() < 0.3
    gives = rnd.random() < 0.5
    for d in SUNDAYS:
        if d < start or (lapse_on and d > lapse_on):
            continue
        p = p_attend * (0.6 if lapse_on and (lapse_on - d).days < 120 else 1) * (0.7 if d.month in (6, 7) else 1)
        if rnd.random() > p:
            continue
        for (m, child, age) in members:
            if child:
                ev = "2" if age < 11 else "4"
            else:
                ev = "5" if age < 30 else "1"
            if rnd.random() < 0.9:
                checkins.append({"type": "CheckIn", "id": str(len(checkins)), "attributes": {
                    "created_at": ts(d), "kind": "Regular", "one_time_guest": False},
                    "relationships": {"person": rel("Person", m), "event": rel("Event", ev),
                                      "event_period": rel("EventPeriod", None),
                                      "event_times": {"data": [{"type": "EventTime", "id": f"{d}-{9 if m % 2 else 11}"}]}}})
            if serves and not child and rnd.random() < 0.4:
                plan_people.append((d, m))
        if gives and rnd.random() < 0.8:
            donations.append({"type": "Donation", "id": str(len(donations)), "attributes": {
                "received_at": ts(d), "amount_cents": 5000, "refunded": False, "payment_status": "succeeded"},
                "relationships": {"person": rel("Person", members[0][0])}})
        if in_group and d.weekday() == 6:
            group_att.setdefault(d, []).extend(m for m, c, _ in members if not c)

# One-time guests
for d in SUNDAYS[-50:]:
    for _ in range(rnd.randint(0, 3)):
        checkins.append({"type": "CheckIn", "id": str(len(checkins)), "attributes": {
            "created_at": ts(d), "kind": "Guest", "one_time_guest": True},
            "relationships": {"person": rel("Person", None), "event": rel("Event", "1")}})

event_times = [{"type": "EventTime", "id": f"{d}-{h}", "attributes": {"starts_at": ts(d, h + 5)}}
               for d in SUNDAYS for h in (9, 11)]
write("people", people)
write("households", households)
write("campuses", [{"type": "Campus", "id": "1", "attributes": {"name": "Shreveport Campus"}}])
write("checkin_events", [{"type": "Event", "id": k, "attributes": {"name": v}} for k, v in EVENTS.items()])
write("checkins", checkins, included=event_times)
write("donations", donations)
write("groups", [{"type": "Group", "id": "77", "attributes": {"name": "Tuesday Group"},
                  "relationships": {"group_type": rel("GroupType", None)}}])
write("group_members/77", [{"type": "Membership", "id": str(i), "attributes": {"role": "member", "joined_at": ts(START)},
                            "relationships": {"person": rel("Person", m)}}
                           for i, m in enumerate(sorted({m for v in group_att.values() for m in v}))])
gev = [{"type": "Event", "id": str(i), "attributes": {"starts_at": ts(d + dt.timedelta(days=2), 23), "canceled": False}}
       for i, d in enumerate(sorted(group_att))]
write("group_events/77", gev)
for e, d in zip(gev, sorted(group_att)):
    write(f"group_attendance/{e['id']}", [{"type": "Attendance", "id": f"{e['id']}-{m}",
                                           "attributes": {"attended": True, "role": "member"},
                                           "relationships": {"person": rel("Person", m)}} for m in group_att[d]])
write("service_types", [{"type": "ServiceType", "id": "5", "attributes": {"name": "Sunday"}}])
plans = sorted({d for d, _ in plan_people})
write("plans/5", [{"type": "Plan", "id": str(i), "attributes": {"sort_date": ts(d)}} for i, d in enumerate(plans)])
pidx = {d: i for i, d in enumerate(plans)}
by_plan = {}
for d, m in plan_people:
    by_plan.setdefault(pidx[d], []).append(m)
for i, ms in by_plan.items():
    write(f"plan_people/5/{i}", [{"type": "PlanPerson", "id": f"{i}-{m}", "attributes": {"status": "C"},
                                  "relationships": {"person": rel("Person", m), "team": rel("Team", 3)}} for m in ms],
          included=[{"type": "Team", "id": "3", "attributes": {"name": "Guest Services"}}])
write("event_times", [{"type": "EventTime", "id": f"t{i}", "attributes": {"starts_at": ts(d)},
                       "relationships": {"event": rel("Event", "1"),
                                         "headcounts": {"data": [{"type": "Headcount", "id": f"h{i}"}]}}}
                      for i, d in enumerate(SUNDAYS)],
      included=[{"type": "Headcount", "id": f"h{i}", "attributes": {"total": 700 + rnd.randint(-80, 80)}}
                for i in range(len(SUNDAYS))])
print(f"fixture: {len(people)} people, {len(checkins)} check-ins, {len(donations)} gifts -> {RAW_DIR}")
