"""Private call list: adult first-time guests (last 12 months) who never attended
Discover Celebration / Growth Track. Uses the same newcomer rule as analyze.py.

Writes out/private/discover_call_list.csv. Run after analyze.py.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

import analyze as A
import config as C

DISCOVER = r"Discover Celebration|Growth Track"


def main():
    t = A.load()
    a, W = t["activity"], C.windows()
    names = dict(zip(t["events"]["event_id"], t["events"]["name"]))
    a = a.assign(ename=a["event_id"].map(names).fillna(""))
    went = set(a.loc[a["ename"].str.contains(DISCOVER), "person_id"])

    att = A.attendance(a)
    first_any = a.groupby("person_id")["date"].min()
    first_att = att.groupby("person_id")["date"].min()
    last_att = att.groupby("person_id")["date"].max()
    visits = att.groupby("person_id").size()
    p = t["people"].set_index("person_id")
    grace = dt.timedelta(days=C.NEW_PERSON_GRACE_DAYS)
    connect = a[a["source"].isin(["group", "serve"]) |
                ((a["source"] == "checkin") & (a["kind"] == "volunteer"))]
    connected = set(connect["person_id"])

    hh = t["households"]
    kids_in_hh = {}
    if len(hh):
        bd = p["birthdate"]
        hh = hh.assign(kid=hh["person_id"].map(
            lambda x: isinstance(bd.get(x), dt.date) and (C.AS_OF - bd.get(x)).days < 18 * 365.25))
        per_hh = hh.groupby("household_id")["kid"].sum()
        main = hh.drop_duplicates("person_id").set_index("person_id")["household_id"]
        kids_in_hh = main.map(per_hh).to_dict()

    rows = []
    for pid, first in first_att.items():
        if not (W["newcomer"][0] <= first <= C.AS_OF) or first_any.get(pid) != first:
            continue
        created = p["created_at"].get(pid)
        if not (isinstance(created, dt.date) and created >= first - grace):
            continue
        b = p["birthdate"].get(pid)
        age = (C.AS_OF - b).days / 365.25 if isinstance(b, dt.date) else None
        is_child = str(p["child"].get(pid)).lower() == "true" or (age is not None and age < 18)
        if is_child or pid in went:
            continue
        last = last_att.get(pid)
        days_since = (C.AS_OF - last).days
        n = int(visits.get(pid, 0))
        # Priority: recent and returning guests first.
        tier = ("1 - came back, seen in last 30 days" if n >= 2 and days_since <= 30 else
                "2 - came back, seen in last 90 days" if n >= 2 and days_since <= 90 else
                "3 - one visit, last 60 days" if days_since <= 60 else
                "4 - not seen in 60+ days")
        rows.append({
            "priority": tier, "first_name": p["first_name"].get(pid), "last_name": p["last_name"].get(pid),
            "age": int(age) if age is not None else "", "first_visit": first, "visits": n,
            "last_visit": last, "days_since": days_since,
            "kids_in_household": int(kids_in_hh.get(pid, 0) or 0),
            "in_group_or_serving": "yes" if pid in connected else "",
            "pco_link": f"https://people.planningcenteronline.com/people/AC{pid}",
        })
    df = pd.DataFrame(rows).sort_values(["priority", "days_since", "visits"], ascending=[True, True, False])
    C.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(C.PRIVATE_DIR / "discover_call_list.csv", index=False)
    write_html(df)
    print(len(df), "people")
    print(df["priority"].value_counts().sort_index().to_string())
    print("with kids at home:", int((df["kids_in_household"] > 0).sum()),
          "| already in a group or serving:", int((df["in_group_or_serving"] == "yes").sum()))


def write_html(df: pd.DataFrame):
    import html
    rows = []
    for _, r in df.iterrows():
        name = f'<a href="{html.escape(r["pco_link"])}">{html.escape(str(r["first_name"]))} {html.escape(str(r["last_name"]))}</a>'
        cells = [html.escape(str(r["priority"]))[:1], name, r["age"], r["first_visit"], r["visits"], r["last_visit"],
                 r["kids_in_household"] or "", r["in_group_or_serving"]]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    counts = df["priority"].value_counts().sort_index()
    legend = "".join(f"<li><b>{html.escape(k[:1])}</b> {html.escape(k[4:])}: {v}</li>" for k, v in counts.items())
    page = f"""<title>Discover Celebration Call List</title>
<style>
:root {{ --bg:#f6f5f2; --fg:#262524; --muted:#6f6b66; --line:#e3e0da; --accent:#3f5a9c; --warn:#9a3412;
  --sans:'Hanken Grotesk','Helvetica Neue',Helvetica,Arial,system-ui,sans-serif }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#121412; --fg:#f0efec; --muted:#9a968f; --line:#2c2c2a; --accent:#9db0e6; --warn:#fdba74; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#121412; --fg:#f0efec; --muted:#9a968f; --line:#2c2c2a; --accent:#9db0e6; --warn:#fdba74; color-scheme:dark }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 var(--sans); padding:28px 16px }}
main {{ max-width:1000px; margin:0 auto; display:grid; gap:14px }}
h1 {{ margin:0; font-size:28px }} p, ul {{ margin:0; max-width:75ch }} a {{ color:var(--accent) }}
.warn {{ color:var(--warn); font-weight:700 }}
.tw {{ overflow-x:auto }} table {{ border-collapse:collapse; width:100%; font-size:13.5px }}
th,td {{ text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); white-space:nowrap }}
th {{ font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted) }}
</style>
<main>
<p class="warn">Internal: guest team follow-up only. Do not share outside staff.</p>
<h1>Discover Celebration call list</h1>
<p>Adult first-time guests from {C.windows()["newcomer"][0]:%b %d, %Y} to {C.AS_OF:%b %d, %Y} who have not attended Discover Celebration.
Guests who went to Discover became regular attenders at about four times the rate of guests who didn't. Call priority 1 first; open a name to see their contact details in Planning Center.</p>
<ul>{legend}</ul>
<div class="tw"><table><thead><tr><th>Priority</th><th>Name</th><th>Age</th><th>First visit</th><th>Visits</th><th>Last visit</th><th>Kids at home</th><th>In group / serving</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
</main>"""
    (C.PRIVATE_DIR / "discover_call_list.html").write_text(page)


if __name__ == "__main__":
    main()
