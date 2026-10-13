"""Render the shareable dashboard and the private at-risk page.

  out/dashboard.html          aggregates only, safe to share with staff
  out/private/at_risk.html    names; keep inside the pastoral team

Narrative text (summary, findings, recommendations, data-gap notes) comes from
narrative.json, written after reviewing the numbers. If it is missing the
dashboard still renders with the charts and definitions.
"""
from __future__ import annotations

import html
import json

import pandas as pd

import config as C

TEMPLATE = C.ROOT / "dashboard_template.html"
NARRATIVE = C.ROOT / "narrative.json"


def safe_json(obj) -> str:
    return json.dumps(obj, default=str).replace("</", "<\\/")


def render_dashboard():
    metrics = json.loads((C.OUT_DIR / "metrics.json").read_text())
    narrative = json.loads(NARRATIVE.read_text()) if NARRATIVE.exists() else {}
    page = (TEMPLATE.read_text()
            .replace("/*__METRICS__*/", safe_json(metrics))
            .replace("/*__NARRATIVE__*/", safe_json(narrative)))
    (C.OUT_DIR / "dashboard.html").write_text(page)


def render_private():
    path = C.PRIVATE_DIR / "at_risk.csv"
    if not path.exists():
        return
    risk = pd.read_csv(path, dtype=str).fillna("")
    lapsed = pd.read_csv(C.PRIVATE_DIR / "lapsed.csv", dtype=str).fillna("") \
        if (C.PRIVATE_DIR / "lapsed.csv").exists() else pd.DataFrame()

    def table(df, cols, labels):
        head = "".join(f"<th>{html.escape(lab)}</th>" for lab in labels)
        body = []
        for _, r in df.iterrows():
            cells = []
            for c in cols:
                v = html.escape(str(r.get(c, "")))
                if c == "name":
                    v = f'<a href="{html.escape(r["pco_link"])}">{html.escape(r["first_name"])} {html.escape(r["last_name"])}</a>'
                cells.append(f"<td>{v}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        return f"<div class='tw'><table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"

    W = C.windows()
    page = f"""<title>At-Risk Follow-Up List</title>
<style>
:root {{ --bg:#f6f5f2; --fg:#262524; --muted:#6f6b66; --line:#e3e0da; --accent:#3f5a9c; --warn:#9a3412;
  --sans:'Hanken Grotesk','Helvetica Neue',Helvetica,Arial,system-ui,sans-serif }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#121412; --fg:#f0efec; --muted:#9a968f; --line:#2c2c2a; --accent:#9db0e6; --warn:#fdba74; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#121412; --fg:#f0efec; --muted:#9a968f; --line:#2c2c2a; --accent:#9db0e6; --warn:#fdba74; color-scheme:dark }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 var(--sans); padding:28px 16px }}
main {{ max-width:1100px; margin:0 auto; display:grid; gap:18px }}
h1 {{ margin:0; font-size:28px }} h2 {{ margin:8px 0 0; font-size:19px }}
.warn {{ color:var(--warn); font-weight:700 }}
p {{ margin:0; max-width:75ch }} a {{ color:var(--accent) }}
.tw {{ overflow-x:auto }} table {{ border-collapse:collapse; width:100%; font-size:13.5px }}
th,td {{ text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); white-space:nowrap }}
th {{ font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--muted) }}
</style>
<main>
<p class="warn">Private: pastoral follow-up only. Do not share, project or post.</p>
<h1>At-risk follow-up list</h1>
<p>Data as of {C.AS_OF:%b %d, %Y}. <b>{len(risk)}</b> people were regular attenders (6+ attendance days)
between {W['at_risk_prior'][0]:%b %d} and {W['at_risk_prior'][1]:%b %d, %Y} and have attended at least
{int(C.AT_RISK_DROP * 100)}% less since. Sorted by the size of the drop. "Other signals" compares the same two windows.
Check the household before calling: one family member's check-ins can drop simply because a child aged out of kids' ministry.</p>
{table(risk, ["name", "age", "membership", "prior_90d_attendances", "last_90d_attendances", "drop_pct", "last_attended", "days_since", "other_signals"],
       ["Name", "Age", "Membership", "Prior 3 mo", "Last 3 mo", "Drop %", "Last attended", "Days since", "Other signals"])}
<h2>Already lapsed ({len(lapsed)})</h2>
<p>Regular attenders a year ago with no activity of any kind in the last 90 days, most recent first.</p>
{table(lapsed, ["name", "age_band", "household_type", "ministry_area", "engagement", "last_attended", "status", "membership"],
       ["Name", "Age band", "Household", "Ministry", "Engagement a year ago", "Last attended", "PCO status", "Membership"]) if len(lapsed) else ""}
</main>"""
    (C.PRIVATE_DIR / "at_risk.html").write_text(page)


if __name__ == "__main__":
    render_dashboard()
    render_private()
    print("wrote", C.OUT_DIR / "dashboard.html", "and", C.PRIVATE_DIR / "at_risk.html")
