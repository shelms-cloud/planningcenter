"""Pull the raw Planning Center data the analysis needs.

Auth: a Planning Center Personal Access Token, read from the environment as
PCO_APP_ID and PCO_SECRET (https://api.planningcenteronline.com/oauth/applications).
The token's user needs read access to People, Check-Ins, Groups, Services and Giving.

Every API page is saved untouched under data/raw/<resource>/ so any number on
the dashboard can be traced back to the records it came from. Re-running skips
pages already on disk; delete data/raw to force a full refresh.

Usage:  python3 attrition/fetch_pco.py [people checkins headcounts groups services giving]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from config import HISTORY_START, RAW_DIR

API = "https://api.planningcenteronline.com"
session = requests.Session()


def _auth() -> tuple[str, str]:
    app_id, secret = os.environ.get("PCO_APP_ID"), os.environ.get("PCO_SECRET")
    if not app_id or not secret:
        sys.exit("Set PCO_APP_ID and PCO_SECRET (a Planning Center Personal Access Token).")
    return app_id, secret


def get(url: str) -> dict:
    for attempt in range(8):
        r = session.get(url, auth=_auth(), timeout=60)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("Retry-After", "5")) + 1)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"giving up on {url}")


def paginate(name: str, path: str, params: dict, stop=None) -> list[Path]:
    """Fetch every page of `path`, saving each to data/raw/<name>/NNNNN.json.

    `stop(page_json) -> bool` lets a caller end early on date-sorted endpoints.
    """
    out = RAW_DIR / name
    out.mkdir(parents=True, exist_ok=True)
    done = out / "_complete"
    if done.exists():
        return sorted(out.glob("*.json"))
    url = f"{API}{path}?{urlencode({'per_page': 100, **params})}"
    n = 0
    while url:
        page = get(url)
        (out / f"{n:05d}.json").write_text(json.dumps(page))
        n += 1
        if stop and stop(page):
            break
        url = page.get("links", {}).get("next")
        if n % 25 == 0:
            print(f"  {name}: {n} pages", flush=True)
    done.write_text(str(n))
    print(f"  {name}: done, {n} pages", flush=True)
    return sorted(out.glob("*.json"))


def ids_in(name: str) -> list[dict]:
    rows = []
    for f in sorted((RAW_DIR / name).glob("*.json")):
        rows.extend(json.loads(f.read_text()).get("data", []))
    return rows


def _older_than(field: str, cutoff: str):
    """Stop paging a newest-first list once a whole page predates `cutoff`."""
    def stop(page):
        vals = [(d.get("attributes") or {}).get(field) or "" for d in page.get("data", [])]
        return bool(vals) and max(vals) < cutoff
    return stop


START = HISTORY_START.isoformat()


def fetch_people():
    paginate("people", "/people/v2/people", {
        "include": "primary_campus",
        "fields[Person]": "first_name,last_name,given_name,nickname,birthdate,child,grade,"
                          "gender,membership,status,created_at,inactivated_at,primary_campus",
    })
    paginate("households", "/people/v2/households", {"include": "people"})
    paginate("campuses", "/people/v2/campuses", {})


def fetch_checkins():
    paginate("checkin_events", "/check-ins/v2/events", {})
    # Newest first, stop once we pass the history start. event_period gives the
    # actual service date (Sunday adult check-ins are often entered after service).
    paginate("checkins", "/check-ins/v2/check_ins", {
        "order": "-created_at",
        "include": "event,event_period,event_times",
        "fields[CheckIn]": "created_at,kind,one_time_guest,event,event_period,event_times,person",
    }, stop=_older_than("created_at", START))


def fetch_headcounts():
    paginate("event_times", "/check-ins/v2/event_times", {
        "order": "-starts_at", "include": "headcounts,event",
    }, stop=_older_than("starts_at", START))


def fetch_groups():
    paginate("groups", "/groups/v2/groups", {"include": "group_type"})
    for g in ids_in("groups"):
        gid = g["id"]
        paginate(f"group_members/{gid}", f"/groups/v2/groups/{gid}/memberships", {})
        paginate(f"group_events/{gid}", f"/groups/v2/groups/{gid}/events",
                 {"order": "-starts_at"}, stop=_older_than("starts_at", START))
    for gdir in sorted((RAW_DIR / "group_events").iterdir()):
        for ev in ids_in(f"group_events/{gdir.name}"):
            a = ev["attributes"]
            if (a.get("starts_at") or "") < START or a.get("canceled"):
                continue
            paginate(f"group_attendance/{ev['id']}",
                     f"/groups/v2/events/{ev['id']}/attendances", {})


def fetch_services():
    paginate("service_types", "/services/v2/service_types", {})
    for st in ids_in("service_types"):
        sid = st["id"]
        paginate(f"plans/{sid}", f"/services/v2/service_types/{sid}/plans",
                 {"filter": "after", "after": START, "order": "sort_date"})
        for plan in ids_in(f"plans/{sid}"):
            if (plan["attributes"].get("sort_date") or "") > time.strftime("%Y-%m-%dT23:59"):
                continue  # future plans: not activity yet
            paginate(f"plan_people/{sid}/{plan['id']}",
                     f"/services/v2/service_types/{sid}/plans/{plan['id']}/team_members",
                     {"include": "team"})


def fetch_giving():
    paginate("donations", "/giving/v2/donations", {
        "order": "-received_at",
        "fields[Donation]": "received_at,amount_cents,refunded,payment_status,person",
    }, stop=_older_than("received_at", START))


STEPS = {
    "people": fetch_people,
    "checkins": fetch_checkins,
    "headcounts": fetch_headcounts,
    "groups": fetch_groups,
    "services": fetch_services,
    "giving": fetch_giving,
}

if __name__ == "__main__":
    for step in sys.argv[1:] or STEPS:
        print(f"fetching {step} ...", flush=True)
        STEPS[step]()
