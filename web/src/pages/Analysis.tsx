import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadAnalysis, loadDrugFamilies } from "../data";
import type { Analysis, Comparison, DrugFamily, Finding, LlmComparison } from "../types";
import { Criteria } from "../components/Criteria";

const FL = "Florida Blue";
const OS = "Oscar";

export default function AnalysisPage() {
  const [a, setA] = useState<Analysis | null>(null);
  useEffect(() => {
    loadAnalysis().then(setA);
  }, []);
  if (!a) return <div className="loading">Running the analysis…</div>;
  const s = a.summary;

  return (
    <div className="report">
      <div className="report-hero">
        <h1>Coverage Comparison: Florida Blue vs. Oscar Health</h1>
        <p className="report-lede">
          A side-by-side analysis of {s.total_policies.toLocaleString()} medical &amp;
          drug coverage policies — where the two payers agree, where their coverage
          criteria diverge, and where only one publishes a policy.
        </p>
        <div className="kpi-row">
          <Kpi n={s.cross_payer_topics} label="overlapping topics" sub="matched across both payers" />
          <Kpi n={s.topics_with_diffs} label="show criteria differences" sub="of the overlapping topics" accent />
          <Kpi n={s.bcbsfl_only} label="Florida Blue only" sub="dedicated guideline" cls="src-bcbsfl-text" />
          <Kpi n={s.oscar_only} label="Oscar only" sub="dedicated guideline" cls="src-oscar-text" />
        </div>
        <p className="hero-foot">
          Plus <strong>{(s as any).drug_family_links ?? ""}</strong> Florida Blue per-drug policies
          that map to <strong>{(s as any).drug_families ?? ""}</strong> consolidated Oscar drug-class
          guidelines — see “Drug families” below.</p>
      </div>

      <Section title="How to read this" subtle>
        <p className="note">
          Policies were scraped from each payer's public clinical-guideline site and
          matched into topics automatically by title/text similarity. <strong>Coverage-criteria
          excerpts and difference tags are extracted programmatically</strong> (Florida Blue's
          consolidated drug policies are followed to their parent class guideline); the{" "}
          <strong>Key Findings below were written after reading the matched policies</strong>.
          “Only one payer” counts reflect <em>who publishes a dedicated guideline</em> — not a
          definitive coverage yes/no, since a payer may handle a service under a broader policy,
          delegate it to a vendor (Oscar routes advanced imaging to eviCore), or address it in plan
          documents.
        </p>
      </Section>

      <Section title="Key findings">
        <div className="findings">
          {a.findings.map((f) => (
            <FindingCard key={f.id} f={f} />
          ))}
        </div>
      </Section>

      <Section title="What drives the differences"
        subtitle="Across the 99 overlapping topics, how often each requirement appears on one payer but not the other (automated scan).">
        <div className="diffbars">
          {Object.entries(s.diff_type_counts).map(([label, n]) => (
            <div className="diffbar" key={label}>
              <span className="diffbar-label">{label}</span>
              <span className="diffbar-track">
                <span className="diffbar-fill" style={{ width: `${(n / s.cross_payer_topics) * 100}%` }} />
              </span>
              <span className="diffbar-n">{n}</span>
            </div>
          ))}
        </div>
      </Section>

      {s.restrictiveness && s.restrictiveness.scored > 0 && (
        <Section title="Who runs tighter criteria"
          subtitle="Across topics with an AI-read comparison, which payer is harder to get approved under. Tighter criteria likely lower utilization and cost for that payer — but can drive member and provider abrasion, so weigh against the actual cost of each service.">
          <Restrictiveness r={s.restrictiveness} labels={s.source_labels} />
        </Section>
      )}

      <Section title="Topic-by-topic comparison"
        subtitle="Every overlapping topic with its extracted coverage criteria. Open one to read both side by side.">
        <ComparisonTable comparisons={a.comparisons} />
      </Section>

      <Section title="Drug families: one Oscar guideline vs. many Florida Blue policies"
        subtitle="Where title-matching can't reach: Oscar bundles a drug class into a single guideline; Florida Blue publishes a separate policy per drug. Matched by reading the drug list inside each Oscar class guideline.">
        <DrugFamilies />
      </Section>

      <Section title="Coverage gaps"
        subtitle="Topics where only one payer publishes a dedicated guideline (see caveat above).">
        <GapColumns a={a} />
      </Section>
    </div>
  );
}

function DrugFamilies() {
  const [fams, setFams] = useState<DrugFamily[] | null>(null);
  useEffect(() => {
    loadDrugFamilies().then(setFams);
  }, []);
  if (!fams) return <div className="muted">Loading drug families…</div>;
  return (
    <div className="families">
      {fams.map((f) => (
        <div key={f.oscar_class.policy_id} className="family">
          <div className="family-oscar">
            <span className="src-chip src-oscar">{OS}</span>
            <Link to={`/policy/${f.oscar_class.id}`} className="family-class">
              {f.oscar_class.title}
            </Link>
            <span className="mono dim">{f.oscar_class.policy_id}</span>
            <div className="family-note">1 combined guideline</div>
          </div>
          <div className="family-arrow">→</div>
          <div className="family-fl">
            <div className="family-fl-head">
              <span className="src-chip src-bcbsfl">{FL}</span>
              <span className="dim">{f.n_matched_bcbsfl} separate policies</span>
            </div>
            <div className="family-drugs">
              {f.members.filter((m) => m.bcbsfl).map((m) => (
                <Link key={m.bcbsfl!.policy_id} to={`/policy/${m.bcbsfl!.id}`} className="family-drug">
                  <span className="fd-name">{drugName(m.bcbsfl!.title, m.drug)}</span>
                  <span className="mono dim">{m.bcbsfl!.policy_id}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Prefer the brand from the Florida Blue title (handles Oscar sub-brand fragments).
function drugName(flTitle: string, fallback: string): string {
  const m = flTitle.match(/\(([^)]+)\)/);
  if (m) return m[1].split(/[,;]/)[0].trim();
  return flTitle.split(/[(,]/)[0].trim() || fallback;
}

function Kpi({ n, label, sub, accent, cls }: { n: number; label: string; sub: string; accent?: boolean; cls?: string }) {
  return (
    <div className={`kpi ${accent ? "kpi-accent" : ""}`}>
      <div className={`kpi-n ${cls || ""}`}>{n.toLocaleString()}</div>
      <div className="kpi-label">{label}</div>
      <div className="kpi-sub">{sub}</div>
    </div>
  );
}

function Section({ title, subtitle, subtle, children }: { title: string; subtitle?: string; subtle?: boolean; children: React.ReactNode }) {
  return (
    <section className={`report-section ${subtle ? "subtle" : ""}`}>
      <h2>{title}</h2>
      {subtitle && <p className="section-sub">{subtitle}</p>}
      {children}
    </section>
  );
}

const TIER_LABEL: Record<string, string> = { major: "Major", notable: "Notable" };
const TYPE_LABEL: Record<string, string> = {
  criteria: "Criteria difference", organization: "Structure", gap: "Scope", agreement: "Agreement",
};

function FindingCard({ f }: { f: Finding }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`finding finding-${f.type}`}>
      <button className="finding-head" onClick={() => setOpen((o) => !o)}>
        <div className="finding-tags">
          <span className={`tier tier-${f.tier}`}>{TIER_LABEL[f.tier]}</span>
          <span className="ftype">{TYPE_LABEL[f.type]}</span>
        </div>
        <h3>{f.title}</h3>
        <p className="finding-summary">{f.summary}</p>
        <span className="finding-toggle">{open ? "Hide detail −" : "Read detail +"}</span>
      </button>
      {open && (
        <div className="finding-detail">
          <p dangerouslySetInnerHTML={{ __html: mdInline(f.detail) }} />
          {f.examples.length > 0 && (
            <div className="finding-examples">
              <span>Compare:</span>
              {f.examples.map((e) => (
                <Link key={e.topic_id} to={`/topic/${e.topic_id}`} className="ex-link">
                  {e.label}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// The coverage requirements we track and align side-by-side. Order = display order.
const REQUIREMENTS: { key: string; label: string }[] = [
  { key: "prior_auth", label: "Prior authorization" },
  { key: "step_therapy", label: "Step therapy (try & fail first)" },
  { key: "age_limit", label: "Age restriction" },
  { key: "specialist", label: "Specialist prescriber" },
  { key: "quantity", label: "Quantity / dose limit" },
  { key: "experimental", label: "Some uses experimental / investigational" },
];

function ComparisonTable({ comparisons }: { comparisons: Comparison[] }) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("all");
  const [openId, setOpenId] = useState<number | null>(null);

  const cats = useMemo(
    () => ["all", ...Array.from(new Set(comparisons.map((c) => c.category))).sort()],
    [comparisons]
  );
  const rows = useMemo(() => {
    const n = q.trim().toLowerCase();
    return comparisons
      .filter((c) => (cat === "all" ? true : c.category === cat))
      .filter((c) => (n ? c.label.toLowerCase().includes(n) : true));
  }, [comparisons, q, cat]);

  return (
    <div>
      <div className="toolbar">
        <input className="search" placeholder="Filter topics…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="select" value={cat} onChange={(e) => setCat(e.target.value)}>
          {cats.map((c) => <option key={c} value={c}>{c === "all" ? "All categories" : c}</option>)}
        </select>
        <span className="count">{rows.length} topics</span>
      </div>
      <div className="cmp-table">
        {rows.map((c) => {
          const open = openId === c.topic_id;
          const n = diffCount(c);
          return (
            <div key={c.topic_id} className={`cmp ${open ? "open" : ""}`}>
              <button className="cmp-head" onClick={() => setOpenId(open ? null : c.topic_id)}>
                <span className="cmp-label">
                  {c.label}
                  {c.llm_matched && <span className="ai-badge" title="Matched by AI subject normalization">AI-matched</span>}
                </span>
                <span className="cmp-cat">{c.category}</span>
                <span className={`cmp-status ${n === 0 ? "is-aligned" : "is-diff"}`}>
                  {n === 0
                    ? "Criteria aligned"
                    : `${n} requirement${n === 1 ? "" : "s"} differ`}
                </span>
                <span className="cmp-caret">{open ? "−" : "+"}</span>
              </button>
              {open && <ComparisonBody c={c} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function diffCount(c: Comparison): number {
  if (c.llm) {
    return (
      c.llm.florida_blue_only.length +
      c.llm.oscar_only.length +
      c.llm.shared.filter((s) => s.agreement === "differs").length
    );
  }
  return c.diffs.length;
}

function ComparisonBody({ c }: { c: Comparison }) {
  return (
    <div className="cmp-body">
      {c.llm ? <LlmView llm={c.llm} /> : <HeuristicView c={c} />}

      {/* Source criteria, side by side, for reference. Without an LLM comparison
          we also tint shared (green) vs one-payer-only (orange) wording. */}
      <details className="cmp-source">
        <summary>Source criteria text</summary>
        {!c.llm && (
          <p className="cmp-legend">
            <span className="legend-swatch shared" /> wording shared with the other payer
            <span className="legend-swatch unique" /> appears on this payer only
          </p>
        )}
        <div className="cmp-sides">
          {(["bcbsfl", "oscar"] as const).map((src) => {
            const side = c[src];
            const other = src === "bcbsfl" ? c.oscar : c.bcbsfl;
            return (
              <div key={src} className="cmp-side">
                <div className="cmp-sidehead">
                  <span className={`src-chip ${src === "bcbsfl" ? "src-bcbsfl" : "src-oscar"}`}>
                    {src === "bcbsfl" ? FL : OS}
                  </span>
                  <span className="mono dim">{side.policy_id || "—"}</span>
                  {side.consolidated_into && (
                    <span className="consol">via class guideline {side.consolidated_into}</span>
                  )}
                </div>
                <Link to={`/policy/${side.id}`} className="cmp-title">{side.title}</Link>
                <Criteria text={side.excerpt} compareTo={c.llm ? undefined : other.excerpt} />
              </div>
            );
          })}
        </div>
      </details>
    </div>
  );
}

// LLM-aligned comparison: a plain summary, the criteria unique to each payer,
// and a row-by-row table of the requirements they share (flagging where the
// specifics differ).
function LlmView({ llm }: { llm: LlmComparison }) {
  const { summary, shared, florida_blue_only: flOnly, oscar_only: osOnly } = llm;
  const differing = shared.filter((s) => s.agreement === "differs").length;

  const r = llm.restrictiveness;
  return (
    <div className="llm">
      {summary && <p className="llm-summary">{summary}</p>}

      {r && r.more_restrictive !== "neither" && r.magnitude !== "none" && (
        <div className={`restr ${r.more_restrictive === FL ? "restr-fl" : "restr-os"}`}>
          <div className="restr-head">
            <span className={`src-chip ${r.more_restrictive === FL ? "src-bcbsfl" : "src-oscar"}`}>
              {r.more_restrictive}
            </span>
            <span className="restr-tag">is more restrictive · {r.magnitude}</span>
          </div>
          <p className="restr-why">{r.rationale}</p>
          {r.cost_note && <p className="restr-cost">{r.cost_note}</p>}
        </div>
      )}
      {r && (r.more_restrictive === "neither" || r.magnitude === "none") && (
        <div className="restr restr-even">
          <span className="restr-tag">Comparable restrictiveness</span>
          {r.rationale && <p className="restr-why">{r.rationale}</p>}
        </div>
      )}

      {(flOnly.length > 0 || osOnly.length > 0) && (
        <div className="llm-only">
          <SoloColumn
            title={FL}
            cls="src-bcbsfl"
            items={flOnly}
            empty="Nothing required here that Oscar doesn't also require."
          />
          <SoloColumn
            title={OS}
            cls="src-oscar"
            items={osOnly}
            empty="Nothing required here that Florida Blue doesn't also require."
          />
        </div>
      )}

      {shared.length > 0 && (
        <div className="llm-shared">
          <div className="llm-shared-head">
            <h4>Requirements both payers share</h4>
            <span className="llm-shared-sub">
              {differing > 0
                ? `${differing} of ${shared.length} differ in the specifics`
                : "specifics align"}
            </span>
          </div>
          <div className="req-matrix">
            <div className="req-row req-head llm-head">
              <span className="req-name">Requirement</span>
              <span className="req-cell"><span className="src-chip src-bcbsfl">{FL}</span></span>
              <span className="req-cell"><span className="src-chip src-oscar">{OS}</span></span>
            </div>
            {shared.map((s, i) => (
              <div key={i} className={`req-row llm-srow ${s.agreement === "differs" ? "is-diff" : ""}`}>
                <span className="req-name">
                  {s.category}
                  <span className={`agree-pill ${s.agreement}`}>
                    {s.agreement === "differs" ? "differs" : "same"}
                  </span>
                </span>
                <span className="req-cell llm-val">{s.florida_blue}</span>
                <span className="req-cell llm-val">{s.oscar}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {shared.length === 0 && flOnly.length === 0 && osOnly.length === 0 && (
        <p className="cmp-verdict aligned">
          No structured criteria could be extracted for this topic — see the source text below.
        </p>
      )}
    </div>
  );
}

function SoloColumn({
  title, cls, items, empty,
}: { title: string; cls: string; items: { category: string; detail: string }[]; empty: string }) {
  return (
    <div className="solo-col">
      <div className="solo-head">
        <span className={`src-chip ${cls}`}>{title}</span>
        <span className="solo-count">only · {items.length}</span>
      </div>
      {items.length === 0 ? (
        <p className="solo-empty">{empty}</p>
      ) : (
        <ul className="solo-list">
          {items.map((it, i) => (
            <li key={i}>
              <span className="solo-cat">{it.category}</span>
              <span className="solo-detail">{it.detail}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Fallback when no LLM comparison is available: the regex-signal requirement matrix.
function HeuristicView({ c }: { c: Comparison }) {
  const flOnly = c.diffs.filter((d) => d.only === FL).map((d) => d.label);
  const osOnly = c.diffs.filter((d) => d.only === OS).map((d) => d.label);
  return (
    <>
      {c.diffs.length === 0 ? (
        <p className="cmp-verdict aligned">
          Both payers apply the same set of tracked requirements on this topic. The wording
          still differs — read the criteria below for specifics.
        </p>
      ) : (
        <div className="cmp-verdict">
          <p>This is where the two policies diverge:</p>
          <ul>
            {osOnly.length > 0 && (
              <li>
                <span className="src-chip src-oscar">{OS}</span> additionally requires{" "}
                <b>{osOnly.join(", ")}</b> — not stated by Florida Blue.
              </li>
            )}
            {flOnly.length > 0 && (
              <li>
                <span className="src-chip src-bcbsfl">{FL}</span> additionally requires{" "}
                <b>{flOnly.join(", ")}</b> — not stated by Oscar.
              </li>
            )}
          </ul>
        </div>
      )}
      <div className="req-matrix">
        <div className="req-row req-head">
          <span className="req-name">Requirement</span>
          <span className="req-cell"><span className="src-chip src-bcbsfl">{FL}</span></span>
          <span className="req-cell"><span className="src-chip src-oscar">{OS}</span></span>
        </div>
        {REQUIREMENTS.map((r) => {
          const fl = !!c.bcbsfl.signals[r.key];
          const os = !!c.oscar.signals[r.key];
          const diff = fl !== os;
          return (
            <div key={r.key} className={`req-row ${diff ? "is-diff" : ""}`}>
              <span className="req-name">{r.label}</span>
              <ReqCell on={fl} diff={diff} />
              <ReqCell on={os} diff={diff} />
            </div>
          );
        })}
      </div>
    </>
  );
}

function ReqCell({ on, diff }: { on: boolean; diff: boolean }) {
  return (
    <span className={`req-cell ${on ? "yes" : "no"} ${diff ? "diff" : ""}`}>
      {on ? <><span className="req-mark">✓</span> Required</> : <span className="req-dash">— not stated</span>}
    </span>
  );
}

function GapColumns({ a }: { a: Analysis }) {
  return (
    <div className="gap-cols">
      {([["bcbsfl", FL, a.gaps.bcbsfl, a.summary.bcbsfl_gap_categories],
         ["oscar", OS, a.gaps.oscar, a.summary.oscar_gap_categories]] as const).map(
        ([src, label, items, catCounts]) => (
          <div key={src} className="gap-col">
            <div className="gap-colhead">
              <span className={`src-chip ${src === "bcbsfl" ? "src-bcbsfl" : "src-oscar"}`}>{label}</span>
              <span className="dim"> only · {items.length} guidelines</span>
            </div>
            <div className="gap-cats">
              {Object.entries(catCounts).slice(0, 8).map(([c, n]) => (
                <span key={c} className="gap-cat"><b>{n}</b> {c}</span>
              ))}
            </div>
            <ul className="gap-list">
              {items.slice(0, 40).map((g) => (
                <li key={g.topic_id}>
                  <Link to={`/topic/${g.topic_id}`}>{g.label}</Link>
                  {g.policy_id && <span className="mono dim"> {g.policy_id}</span>}
                </li>
              ))}
            </ul>
            {items.length > 40 && <div className="dim more">+ {items.length - 40} more</div>}
          </div>
        )
      )}
    </div>
  );
}

function Restrictiveness({
  r, labels,
}: {
  r: { scored: number; by_payer: Record<string, number>; substantial: Record<string, number> };
  labels: Record<string, string>;
}) {
  void labels;
  const fl = r.by_payer[FL] || 0;
  const os = r.by_payer[OS] || 0;
  const even = r.by_payer["neither"] || 0;
  const max = Math.max(fl, os, even, 1);
  const rows: { name: string; cls: string; n: number; sub?: number }[] = [
    { name: `${FL} tighter`, cls: "src-bcbsfl", n: fl, sub: r.substantial[FL] || 0 },
    { name: `${OS} tighter`, cls: "src-oscar", n: os, sub: r.substantial[OS] || 0 },
    { name: "Comparable", cls: "src-other", n: even },
  ];
  return (
    <div className="restr-roll">
      <p className="restr-roll-lede">
        Of <b>{r.scored}</b> AI-compared topics:
      </p>
      <div className="restr-bars">
        {rows.map((row) => (
          <div className="restr-bar" key={row.name}>
            <span className="restr-bar-label">
              <span className={`dot ${row.cls}`} /> {row.name}
            </span>
            <span className="restr-bar-track">
              <span className="restr-bar-fill" style={{ width: `${(row.n / max) * 100}%` }} />
            </span>
            <span className="restr-bar-n">
              {row.n}
              {row.sub ? <span className="restr-bar-sub"> · {row.sub} substantial</span> : null}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// Minimal inline markdown: **bold**, *italic*, `code`.
function mdInline(t: string): string {
  return t
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}
