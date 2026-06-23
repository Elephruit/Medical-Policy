#!/usr/bin/env python3
"""Build a branded PDF summary of the payer-comparison findings.

    python -m scripts.build_report
    # writes report/coverage-comparison.html, then (if Chrome is present)
    # report/Coverage-Comparison-FloridaBlue-vs-Oscar.pdf

Pulls every number live from the exported analysis bundle so the report can't
drift from the site. Beautiful print layout via headless Chrome.
"""
import base64
import html
import json
import re
import subprocess
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "public" / "data"
OUT = ROOT / "report"
REPO = "https://github.com/Elephruit/Medical-Policy"
SITE = "https://payer-policy-cmp-06222027.web.app"
AUTHOR = "Mike Zehrer"
BRAND = "#1f9bd6"
BRAND_DK = "#127bb0"
FL_C = "#1d4ed8"
OS_C = "#ea580c"

CANON = [
    (r"specialist|ologist|prescriber", "Specialist gate"),
    (r"\bage\b|months of age|years of age", "Age limit"),
    (r"step therapy|tried|failed|trial of|prior therap|inadequate", "Step therapy"),
    (r"continuation|continued|reauth|re-auth", "Continuation rules"),
    (r"duration|approval period|approval length|authorization period", "Approval-duration cap"),
    (r"prior authorization|prior auth|preauth", "Prior authorization"),
    (r"genetic|mutation|biomarker|allele", "Genetic testing"),
    (r"diagnos", "Diagnosis confirmation"),
    (r"dose|dosing|quantity|weight|bsa|body surface", "Dose / quantity cap"),
    (r"document|chart|medical record|labor", "Documentation"),
    (r"experimental|investigational|not medically|exclus|non-covered", "Exclusions / non-covered"),
    (r"lab|test|titer|level|screen", "Lab / testing"),
]


def canon(x: str) -> str:
    x = (x or "").lower()
    for rx, lab in CANON:
        if re.search(rx, x):
            return lab
    return (x or "").title()


def lst(d, k):
    v = d.get(k)
    return v if isinstance(v, list) else []


def load():
    a = json.loads((DATA / "analysis.json").read_text())
    meta = json.loads((DATA / "meta.json").read_text())
    return a, meta


def e(s: str) -> str:
    return html.escape(str(s))


def bars(rows, color, unit_max=None):
    mx = unit_max or max((n for _, n in rows), default=1)
    out = ['<div class="bars">']
    for label, n in rows:
        out.append(
            f'<div class="bar"><span class="bl">{e(label)}</span>'
            f'<span class="bt"><span class="bf" style="width:{n/mx*100:.0f}%;background:{color}"></span></span>'
            f'<span class="bn">{n}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def build():
    a, meta = load()
    s = a["summary"]
    comps = a["comparisons"]
    llm = [c for c in comps if c.get("llm")]
    r = s["restrictiveness"]
    tot = sum(r["by_payer"].values()) or 1
    os_n = r["by_payer"].get("Oscar", 0)
    fl_n = r["by_payer"].get("Florida Blue", 0)
    even_n = r["by_payer"].get("neither", 0)
    os_pct = round(os_n / tot * 100)
    fl_pct = round(fl_n / tot * 100)

    oc, fc = Counter(), Counter()
    for c in llm:
        for it in lst(c["llm"], "oscar_only"):
            oc[canon(it.get("category", ""))] += 1
        for it in lst(c["llm"], "florida_blue_only"):
            fc[canon(it.get("category", ""))] += 1

    def dc(c):
        l = c["llm"]
        return (len(lst(l, "oscar_only")) + len(lst(l, "florida_blue_only"))
                + sum(1 for x in lst(l, "shared") if x.get("agreement") == "differs"))
    divergent = sorted(llm, key=dc, reverse=True)[:6]

    logo = base64.b64encode((OUT / "elephruit-logo.png").read_bytes()).decode()
    fl_pol = s["by_source"].get("bcbsfl", 0)
    os_pol = s["by_source"].get("oscar", 0)
    fams = meta.get("drug_families", 0)
    fam_links = meta.get("drug_family_links", 0)
    today = date.today().strftime("%B %Y")

    # ---- key findings (LLM-derived) ----
    findings = []
    findings.append((
        "Oscar runs materially tighter utilization management",
        f"Across the <b>{r['scored']}</b> overlapping drugs and services an LLM read on both "
        f"sides, Oscar imposes the stricter coverage criteria on <b>{os_n} ({os_pct}%)</b> of "
        f"topics versus Florida Blue's <b>{fl_n} ({fl_pct}%)</b>; the rest are comparable. The "
        f"asymmetry holds at the high end: <b>{r['substantial'].get('Oscar',0)}</b> topics are "
        f"<i>substantially</i> tighter on Oscar versus <b>{r['substantial'].get('Florida Blue',0)}</b> "
        f"on Florida Blue. Read as a business signal, Oscar's posture likely suppresses "
        f"utilization and cost — at a higher risk of member and provider abrasion.",
        f'<div class="battle"><span style="width:{os_n/tot*100:.0f}%;background:{OS_C}"></span>'
        f'<span style="width:{even_n/tot*100:.0f}%;background:#cbd3dd"></span>'
        f'<span style="width:{fl_n/tot*100:.0f}%;background:{FL_C}"></span></div>'
        f'<div class="blegend"><span><i style="background:{OS_C}"></i>Oscar tighter {os_n}</span>'
        f'<span><i style="background:#cbd3dd"></i>comparable {even_n}</span>'
        f'<span><i style="background:{FL_C}"></i>Florida Blue tighter {fl_n}</span></div>',
    ))
    findings.append((
        "The two payers tighten in different ways",
        "Counting the requirements each payer imposes that the other doesn't, the <i>shape</i> of "
        "each program is distinct. Oscar leans on <b>access gates</b> — step therapy, age limits, "
        "and specialist-prescriber requirements. Florida Blue leans on <b>operational controls</b> "
        "— dose/quantity limits and continuation-of-therapy rules — with far fewer step-therapy or "
        "specialist gates. Same goal, different levers: Oscar gatekeeps <i>who and when</i>; "
        "Florida Blue controls <i>how much and how long</i>.",
        '<div class="twocol">'
        f'<div><div class="ch ch-os">Oscar adds most often</div>{bars(oc.most_common(6), OS_C)}</div>'
        f'<div><div class="ch ch-fl">Florida Blue adds most often</div>{bars(fc.most_common(6), FL_C)}</div>'
        "</div>",
    ))
    findings.append((
        "Both programs share one backbone: carve-outs and continuation rules",
        f"The single most common 'extra' requirement on <i>both</i> payers is explicit "
        f"<b>exclusions / non-covered uses</b> ({oc.get('Exclusions / non-covered uses',0)} on Oscar, "
        f"{fc.get('Exclusions / non-covered uses',0)} on Florida Blue), and "
        f"<b>continuation-of-therapy rules</b> appear about equally on both "
        f"({oc.get('Continuation-of-therapy rules',0)} vs {fc.get('Continuation-of-therapy rules',0)}). "
        f"Where they differ is everything layered on top of that shared base.",
        None,
    ))
    findings.append((
        "AI subject-normalization recovered matches rule-based matching missed",
        f"Matching policies across payers by document title alone is brittle — the same drug is "
        f"titled differently by each insurer. Normalizing every one of the <b>{s['total_policies']:,}</b> "
        f"policies to a canonical subject with an LLM surfaced <b>{s.get('llm_matched_topics',0)}</b> "
        f"additional cross-payer matches that the deterministic title matcher could not link — same "
        f"drug, different paperwork.",
        None,
    ))
    findings.append((
        "“Coverage gaps” are mostly organizational, not real holes",
        f"Florida Blue publishes <b>{len(a['gaps']['bcbsfl'])}</b> dedicated guidelines with no Oscar "
        f"counterpart, versus <b>{len(a['gaps']['oscar'])}</b> the other way. But much of that gap is "
        f"<i>structure</i>, not coverage: Oscar consolidates whole drug classes into a single guideline "
        f"— <b>{fams}</b> class guidelines stand in for <b>{fam_links}</b> separate Florida Blue per-drug "
        f"policies. A genuine gap analysis has to read content, not count documents.",
        None,
    ))
    # concrete examples
    ex_rows = []
    for c in divergent[:5]:
        rr = c["llm"].get("restrictiveness", {})
        who = rr.get("more_restrictive", "")
        cls = "os" if who == "Oscar" else ("fl" if who == "Florida Blue" else "even")
        tag = f'{who} {rr.get("magnitude","")}'.strip() if who and who != "neither" else "comparable"
        ex_rows.append(
            f'<div class="ex"><div class="ex-h"><span class="ex-name">{e(c["label"])}</span>'
            f'<span class="ex-tag ex-{cls}">{e(tag)}</span></div>'
            f'<p>{e(c["llm"].get("summary",""))}</p></div>'
        )
    findings.append((
        "The sharpest single-drug divergences",
        "The topics where the two payers' criteria differ most — the first places a reviewer should "
        "look. Each summary below is the model's one-line read of the key difference.",
        '<div class="exlist">' + "".join(ex_rows) + "</div>",
    ))

    # curated findings
    curated = a.get("findings", [])
    cur_html = "".join(
        f'<div class="cf"><h4>{e(f["title"])}</h4><p>{e(f["summary"])}</p></div>'
        for f in curated
    )

    findings_html = "".join(
        f'<section class="find"><div class="find-n">{i:02d}</div>'
        f'<div class="find-body"><h3>{title}</h3><p>{body}</p>{viz or ""}</div></section>'
        for i, (title, body, viz) in enumerate(findings, 1)
    )

    doc = f"""<!doctype html><html><head><meta charset="utf-8">
<style>
@page {{ size: Letter; margin: 14mm 14mm 16mm; }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
body {{ font: 11pt/1.5 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #14202e; margin: 0; }}
h1,h2,h3,h4 {{ margin: 0; letter-spacing: -0.3px; }}
p {{ margin: 0; }}
.dim {{ color: #6b7686; }}

.cover {{ display: flex; flex-direction: column; min-height: 247mm; }}
.cover-top {{ border-bottom: 3px solid {BRAND}; padding-bottom: 18px; }}
.logo {{ height: 52px; }}
.cover-mid {{ margin-top: auto; margin-bottom: auto; }}
.eyebrow {{ color: {BRAND_DK}; font-weight: 800; text-transform: uppercase; letter-spacing: 2px; font-size: 10pt; }}
.title {{ font-size: 32pt; line-height: 1.12; margin: 14px 0 10px; font-weight: 800; }}
.title .vs {{ color: {BRAND}; }}
.subtitle {{ font-size: 13pt; color: #44525f; max-width: 150mm; line-height: 1.5; }}
.byline {{ margin-top: 26px; font-size: 11pt; }}
.byline b {{ color: {BRAND_DK}; }}
.links a {{ color: {BRAND_DK}; text-decoration: none; }}
.cover-bot {{ border-top: 1px solid #e6e9ef; padding-top: 14px; display: flex; justify-content: space-between; font-size: 9.5pt; }}

.glance {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 10px; margin: 26px 0; }}
.stat {{ border: 1px solid #e6e9ef; border-radius: 12px; padding: 14px; background: #fafbfd; }}
.stat .n {{ font-size: 24pt; font-weight: 800; letter-spacing: -1px; line-height: 1; }}
.stat .l {{ font-size: 9.5pt; color: #6b7686; margin-top: 6px; line-height: 1.3; }}

.sec-h {{ font-size: 9.5pt; font-weight: 800; text-transform: uppercase; letter-spacing: 2px; color: {BRAND_DK};
  border-bottom: 2px solid {BRAND}; padding-bottom: 6px; margin: 30px 0 16px; }}

.find {{ display: grid; grid-template-columns: 40px 1fr; gap: 14px; margin: 0 0 20px; break-inside: avoid; }}
.find-n {{ font-size: 17pt; font-weight: 800; color: {BRAND}; }}
.find h3 {{ font-size: 14pt; margin-bottom: 6px; }}
.find-body > p {{ color: #2a3744; }}

.battle {{ display: flex; height: 16px; border-radius: 8px; overflow: hidden; margin: 14px 0 6px; }}
.battle span {{ display: block; height: 100%; }}
.blegend {{ display: flex; gap: 18px; font-size: 9.5pt; color: #6b7686; }}
.blegend i {{ display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }}

.bars {{ display: flex; flex-direction: column; gap: 7px; margin-top: 8px; }}
.bar {{ display: grid; grid-template-columns: 120px 1fr 20px; align-items: center; gap: 9px; font-size: 9pt; }}
.bl {{ line-height: 1.15; }}
.bt {{ background: #eef1f5; border-radius: 5px; height: 13px; overflow: hidden; }}
.bf {{ display: block; height: 100%; border-radius: 5px; }}
.bn {{ font-weight: 700; text-align: right; }}
.twocol {{ display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-top: 10px; }}
.ch {{ font-weight: 700; font-size: 10pt; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid #e6e9ef; }}
.ch-os {{ color: {OS_C}; }} .ch-fl {{ color: {FL_C}; }}

.exlist {{ margin-top: 10px; display: flex; flex-direction: column; gap: 10px; }}
.ex {{ border: 1px solid #e6e9ef; border-radius: 10px; padding: 11px 13px; break-inside: avoid; }}
.ex-h {{ display: flex; justify-content: space-between; align-items: baseline; gap: 10px; margin-bottom: 4px; }}
.ex-name {{ font-weight: 700; font-size: 10.5pt; }}
.ex-tag {{ font-size: 8.5pt; font-weight: 800; text-transform: uppercase; letter-spacing: .04em; padding: 2px 7px; border-radius: 5px; white-space: nowrap; }}
.ex-os {{ color: {OS_C}; background: #fdeee4; }} .ex-fl {{ color: {FL_C}; background: #e7eefb; }} .ex-even {{ color:#475569; background:#eef1f5; }}
.ex p {{ font-size: 9.5pt; color: #2a3744; }}

.cfgrid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
.cf {{ border-left: 3px solid {BRAND}; padding: 2px 0 2px 12px; break-inside: avoid; }}
.cf h4 {{ font-size: 10.5pt; margin-bottom: 3px; }}
.cf p {{ font-size: 9.5pt; color: #44525f; }}

.method {{ background: #f6fbfe; border: 1px solid #d6ecf8; border-radius: 12px; padding: 16px 18px; font-size: 10pt; color: #2a3744; line-height: 1.6; }}
.method b {{ color: {BRAND_DK}; }}
.pipe {{ font-family: ui-monospace, Menlo, monospace; font-size: 8.5pt; color: #44525f; background: #fff; border: 1px solid #d6ecf8; border-radius: 8px; padding: 10px 12px; margin-top: 10px; white-space: pre; overflow-x: auto; }}

.appx {{ break-before: page; }}
.stage {{ display: grid; grid-template-columns: 26px 1fr; gap: 12px; margin: 0 0 13px; break-inside: avoid; }}
.stage-n {{ font-size: 12pt; font-weight: 800; color: {BRAND}; }}
.stage h4 {{ font-size: 11pt; margin-bottom: 3px; }}
.stage p {{ font-size: 9.5pt; color: #2a3744; }}
.stage code {{ font-family: ui-monospace, Menlo, monospace; font-size: 8.5pt; background: #eef4f8; padding: 1px 4px; border-radius: 4px; color: {BRAND_DK}; }}
.princ {{ margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
.princ .p {{ border: 1px solid #e6e9ef; border-radius: 10px; padding: 11px 13px; break-inside: avoid; }}
.princ h5 {{ margin: 0 0 3px; font-size: 9.5pt; color: {BRAND_DK}; }}
.princ p {{ margin: 0; font-size: 9pt; color: #44525f; line-height: 1.5; }}

.foot {{ margin-top: 30px; border-top: 1px solid #e6e9ef; padding-top: 12px; display: flex; justify-content: space-between; font-size: 9pt; color: #6b7686; }}
.foot a {{ color: {BRAND_DK}; text-decoration: none; }}
</style></head><body>

<div class="cover">
  <div class="cover-top"><img class="logo" src="data:image/png;base64,{logo}" alt="Elephruit"></div>
  <div class="cover-mid">
    <div class="eyebrow">Competitive Coverage Analysis</div>
    <div class="title">Florida Blue <span class="vs">vs.</span> Oscar Health<br>Medical &amp; Drug Coverage Policies</div>
    <p class="subtitle">An AI-assisted, criterion-by-criterion comparison of {s['total_policies']:,} published
      coverage policies — where the two payers agree, where their requirements diverge, and which payer
      runs the tighter utilization-management criteria.</p>
    <div class="byline">Prepared by <b>{AUTHOR}</b> · {today}</div>
    <div class="byline links">Interactive site: <a href="{SITE}">{SITE.replace('https://','')}</a><br>
      Source &amp; methodology: <a href="{REPO}">{REPO.replace('https://','')}</a></div>
  </div>
  <div class="cover-bot">
    <span>Elephruit · Payer Policy Intelligence</span>
    <span>{fl_pol:,} Florida Blue · {os_pol:,} Oscar policies analyzed</span>
  </div>
</div>

<div class="sec-h">At a glance</div>
<div class="glance">
  <div class="stat"><div class="n" style="color:{OS_C}">{os_pct}%</div><div class="l">of compared topics, <b>Oscar</b> runs the tighter criteria</div></div>
  <div class="stat"><div class="n">{s['cross_payer_topics']}</div><div class="l">overlapping topics matched across both payers</div></div>
  <div class="stat"><div class="n">{s.get('llm_matched_topics',0)}</div><div class="l">matches found only by AI subject-normalization</div></div>
  <div class="stat"><div class="n">{s['total_policies']:,}</div><div class="l">policies scraped, parsed &amp; profiled</div></div>
</div>

<div class="sec-h">Key findings</div>
{findings_html}

<div class="sec-h">Findings from reading the policies</div>
<div class="cfgrid">{cur_html}</div>

<div class="sec-h">How this was built</div>
<div class="method">
  Every policy was scraped from each payer's public clinical-guideline site, parsed from PDF to text,
  then <b>normalized by an LLM</b> into a canonical subject so the same drug or service matches across
  payers even when document titles differ. Overlapping topics were then <b>aligned and scored for
  restrictiveness by an LLM</b> reading both policies' coverage criteria. Restrictiveness is a
  decision-support signal, not ground truth — every claim links back to the source criteria on the
  interactive site. A two-tier model strategy (a fast model for the {s['total_policies']:,} per-policy
  normalizations, a stronger model for the nuanced comparisons) keeps the whole enrichment a bounded,
  cached, reproducible cost.
  <div class="pipe">scrape → extract (PDF→text) → LLM normalize (canonical subject) → match
       → LLM compare + restrictiveness score → static site + this report</div>
</div>

<div class="appx">
<div class="sec-h">Appendix · Methodology &amp; technical flow</div>
<p class="section-sub" style="color:#44525f;font-size:10pt;margin-bottom:18px;max-width:165mm">
  The full pipeline is open source at <b style="color:{BRAND_DK}">{REPO.replace('https://','')}</b>.
  Each stage is a separate, re-runnable command; every LLM call is cached on disk by a content hash,
  so the analysis is incremental and reproducible.</p>

<div class="stage"><div class="stage-n">1</div><div>
  <h4>Acquire</h4><p>A per-payer <code>SourceAdapter</code> yields a catalog and fetches each policy
  PDF. Florida Blue is a stateful ASP.NET/Telerik site crawled by replaying postbacks (sequential);
  Oscar is a Next.js/Contentful site whose PDFs live on a CDN (stateless, parallel). Documents land in
  SQLite with a content hash for change detection.</p></div></div>

<div class="stage"><div class="stage-n">2</div><div>
  <h4>Extract</h4><p>PDF bytes → full text plus structured fields (policy number, authoritative
  subject, effective/revision dates, CPT/HCPCS codes). Source-agnostic.</p></div></div>

<div class="stage"><div class="stage-n">3</div><div>
  <h4>Normalize every policy &nbsp;<span style="color:{BRAND_DK};font-weight:700;font-size:9pt">LLM · fast model</span></h4>
  <p>One call per policy distills it to a <b>canonical subject</b> (generic drug INN or standard
  service name), brand names, type, and key requirements — a payer-agnostic identity key. This is what
  lets the same drug match across insurers when their document titles differ.</p></div></div>

<div class="stage"><div class="stage-n">4</div><div>
  <h4>Match into cross-payer topics</h4><p>A union-find combines two signals: deterministic
  IDF-weighted cosine over title tokens (token-blocked, byte-stable), plus conservative LLM
  same-subject links from stage 3. A topic is flagged <i>AI-matched</i> only when it is cross-payer
  <i>solely</i> because of the LLM links — verified by a baseline diff against the lexical matcher.</p></div></div>

<div class="stage"><div class="stage-n">5</div><div>
  <h4>Compare &amp; score restrictiveness &nbsp;<span style="color:{BRAND_DK};font-weight:700;font-size:9pt">LLM · stronger model</span></h4>
  <p>For each overlapping topic, one call reads both payers' criteria and returns an aligned
  comparison — shared requirements (flagged same/differs), requirements unique to each payer, and a
  restrictiveness verdict (which payer is harder to get approved under, with rationale and a
  cost-vs-abrasion note).</p></div></div>

<div class="stage"><div class="stage-n">6</div><div>
  <h4>Serve</h4><p>Everything exports to a static JSON bundle behind a React/Vite site on Firebase
  Hosting — no database, no server — and to this report.</p></div></div>

<div class="princ">
  <div class="p"><h5>Two-tier model strategy</h5><p>A fast model for the {s['total_policies']:,}
    high-volume normalizations; a stronger model for the ~{len(llm)} nuanced comparisons. Bounded,
    cached, one-time cost.</p></div>
  <div class="p"><h5>Structured output</h5><p>Forced tool-use pins each call to a single schema, so
    every result is valid JSON without bespoke parsing.</p></div>
  <div class="p"><h5>Determinism &amp; idempotence</h5><p>The lexical matcher is byte-stable
    run-to-run; LLM results cache by (prompt version, model, inputs) — re-runs touch only changed
    inputs.</p></div>
  <div class="p"><h5>Decision support, not ground truth</h5><p>Restrictiveness is an LLM judgment over
    PDF-extracted text; every claim links back to the source criteria on the interactive site.</p></div>
</div>
</div>

<div class="foot">
  <span>© {date.today().year} {AUTHOR} · Built with the Elephruit policy-intelligence pipeline</span>
  <span><a href="{REPO}">{REPO.replace('https://','')}</a></span>
</div>

</body></html>"""

    OUT.mkdir(exist_ok=True)
    html_path = OUT / "coverage-comparison.html"
    html_path.write_text(doc)
    print("wrote", html_path)

    pdf_path = OUT / "Coverage-Comparison-FloridaBlue-vs-Oscar.pdf"
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if Path(chrome).exists():
        subprocess.run([
            chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}", html_path.as_uri(),
        ], check=True, capture_output=True)
        print("wrote", pdf_path)
    else:
        print("Chrome not found — open the HTML and Print → Save as PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(build())
