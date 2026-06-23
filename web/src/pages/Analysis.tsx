import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadAnalysis, loadDrugFamilies } from "../data";
import type { Analysis, Comparison, DrugFamily, Finding } from "../types";
import { ComparisonView, RestrictivenessChip, diffCount } from "../components/Comparison";

const FL = "Florida Blue";
const OS = "Oscar";

interface Tally { label: string; n: number; }
interface Insights {
  scored: number;
  oscarAdds: Tally[];
  flAdds: Tally[];
  divergent: { c: Comparison; n: number }[];
}

// The LLM writes free-text category labels, so the same concept fragments
// ("specialist prescriber" / "…requirement" / "…gate"). Bucket them into a
// canonical vocabulary so the leaderboard reads cleanly. Order = priority.
const CANON: [RegExp, string][] = [
  [/specialist|ologist|prescriber/, "Specialist prescriber"],
  [/\bage\b|months of age|years of age/, "Age restriction"],
  [/step therapy|tried|failed|trial of|prior therap|inadequate/, "Step therapy"],
  [/continuation|continued|reauth|re-auth/, "Continuation-of-therapy rules"],
  [/duration|approval period|approval length|authorization period/, "Approval duration limit"],
  [/prior authorization|prior auth|preauth/, "Prior authorization"],
  [/genetic|mutation|biomarker|allele/, "Genetic / biomarker testing"],
  [/diagnos/, "Diagnosis confirmation"],
  [/dose|dosing|quantity|weight|bsa|body surface/, "Dose / quantity limit"],
  [/document|chart|medical record|labor/, "Documentation"],
  [/experimental|investigational|not medically|exclus|non-covered/, "Exclusions / non-covered uses"],
  [/lab|test|titer|level|screen/, "Lab / testing requirement"],
];
function canonCategory(raw: string): string {
  const s = (raw || "").trim().toLowerCase();
  for (const [re, label] of CANON) if (re.test(s)) return label;
  // Fallback: title-case the raw label.
  return raw.trim().replace(/\b\w/g, (m) => m.toUpperCase());
}

function computeInsights(cmps: Comparison[]): Insights {
  const withLlm = cmps.filter((c) => c.llm);
  const tally = (pick: (l: NonNullable<Comparison["llm"]>) => { category: string }[]): Tally[] => {
    const m = new Map<string, Tally>();
    for (const c of withLlm) {
      for (const it of pick(c.llm!)) {
        if (!(it.category || "").trim()) continue;
        const label = canonCategory(it.category);
        const e = m.get(label) || { label, n: 0 };
        e.n++;
        m.set(label, e);
      }
    }
    return [...m.values()].sort((a, b) => b.n - a.n).slice(0, 8);
  };
  return {
    scored: withLlm.length,
    oscarAdds: tally((l) => l.oscar_only),
    flAdds: tally((l) => l.florida_blue_only),
    divergent: withLlm
      .map((c) => ({ c, n: diffCount(c) }))
      .sort((a, b) => b.n - a.n)
      .slice(0, 12),
  };
}

export default function AnalysisPage() {
  const [a, setA] = useState<Analysis | null>(null);
  useEffect(() => {
    loadAnalysis().then(setA);
  }, []);
  if (!a) return <div className="loading">Running the analysis…</div>;
  const s = a.summary;
  const ins = computeInsights(a.comparisons);
  const r = s.restrictiveness;

  return (
    <div className="report">
      <div className="report-hero">
        <span className="report-kicker">AI-read coverage comparison · {ins.scored} drugs &amp; services</span>
        <h1>Florida Blue vs. Oscar Health</h1>
        <p className="report-lede">
          Every overlapping policy, read by an LLM and aligned criterion-by-criterion —
          surfacing where the two payers agree, where their requirements diverge, and
          <strong> which payer runs the tighter coverage criteria</strong>.
        </p>

        {r && r.scored > 0 && <HeadlineVerdict r={r} />}

        <div className="kpi-row">
          <Kpi n={s.cross_payer_topics} label="overlapping topics" sub="matched across both payers" />
          <Kpi n={(s.llm_matched_topics ?? 0)} label="found by AI matching" sub="missed by title matching" accent />
          <Kpi n={s.bcbsfl_only} label="Florida Blue only" sub="dedicated guideline" cls="src-bcbsfl-text" />
          <Kpi n={s.oscar_only} label="Oscar only" sub="dedicated guideline" cls="src-oscar-text" />
        </div>
      </div>

      <Section title="What each payer demands on top"
        subtitle="Across AI-compared topics, the requirement types one payer imposes that the other doesn't — counted from the per-topic “only this payer requires” lists. This is the systematic shape of each payer's tighter posture.">
        <div className="lb-pair">
          <AddLeaderboard title={OS} cls="src-oscar" items={ins.oscarAdds} />
          <AddLeaderboard title={FL} cls="src-bcbsfl" items={ins.flAdds} />
        </div>
      </Section>

      <Section title="Biggest divergences"
        subtitle="The topics where the two payers' criteria differ most — the places worth a human look first. Click through for the full side-by-side.">
        <div className="diverge-grid">
          {ins.divergent.map(({ c, n }) => (
            <Link key={c.topic_id} to={`/topic/${c.topic_id}`} className="diverge-card">
              <span className="diverge-label">{c.label}</span>
              <div className="diverge-foot">
                <span className="diverge-n">{n} differences</span>
                <RestrictivenessChip c={c} />
              </div>
            </Link>
          ))}
        </div>
      </Section>

      <Section title="Key findings">
        <div className="findings">
          {a.findings.map((f) => (
            <FindingCard key={f.id} f={f} />
          ))}
        </div>
      </Section>

      <Section title="What drives the differences"
        subtitle={`Across the ${s.cross_payer_topics} overlapping topics, how often each requirement appears on one payer but not the other (automated regex scan).`}>
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

      <Section title="Every topic, side by side"
        subtitle="All overlapping topics with the AI-aligned criteria comparison. Open one to read the summary, restrictiveness verdict, and matched criteria.">
        <ComparisonTable comparisons={a.comparisons} />
      </Section>

      <Section title="Drug families: one Oscar guideline vs. many Florida Blue policies"
        subtitle="Where title-matching can't reach: Oscar bundles a drug class into a single guideline; Florida Blue publishes a separate policy per drug. Matched by reading the drug list inside each Oscar class guideline.">
        <DrugFamilies />
      </Section>

      <Section title="One payer has a policy, the other doesn't"
        subtitle="Dedicated guidelines published by only one payer — a potential coverage gap (or competitive opening) for the payer that has no counterpart. Each is described from its own policy text. See the method note for the caveat on what 'no policy' means.">
        <GapColumns a={a} />
      </Section>

      <Section title="How this was built" subtle>
        <p className="note">
          Policies were scraped from each payer's public clinical-guideline site, then
          <strong> every policy was normalized by an LLM</strong> into a canonical subject so the
          same drug/service matches across payers even when titles differ
          (<strong>{s.llm_matched_topics ?? 0}</strong> of these matches were found only this way).
          Each overlapping topic's criteria are then <strong>aligned and scored for restrictiveness
          by an LLM</strong> reading both policies' coverage text. Restrictiveness is a
          decision-support signal, not ground truth — the source criteria are one click away on
          every comparison. “Only one payer” counts reflect <em>who publishes a dedicated
          guideline</em>, not a definitive coverage yes/no (a payer may cover a service under a
          broader policy or delegate it to a vendor — e.g. Oscar routes advanced imaging to eviCore).
        </p>
      </Section>
    </div>
  );
}

// Headline: the single biggest takeaway, as a stat + diverging bar.
function HeadlineVerdict({ r }: { r: NonNullable<Analysis["summary"]["restrictiveness"]> }) {
  const os = r.by_payer[OS] || 0;
  const fl = r.by_payer[FL] || 0;
  const even = r.by_payer["neither"] || 0;
  const total = os + fl + even || 1;
  const leader = os >= fl ? OS : FL;
  const leadN = Math.max(os, fl);
  const pct = Math.round((leadN / total) * 100);
  const leadCls = leader === OS ? "src-oscar-text" : "src-bcbsfl-text";
  return (
    <div className="verdict">
      <div className="verdict-stat">
        <span className={`verdict-pct ${leadCls}`}>{pct}%</span>
        <span className="verdict-text">
          of compared topics, <b className={leadCls}>{leader}</b> runs the tighter
          coverage criteria <span className="dim">({leadN} of {total})</span>
        </span>
      </div>
      <div className="battle">
        <span className="battle-seg os" style={{ width: `${(os / total) * 100}%` }} />
        <span className="battle-seg even" style={{ width: `${(even / total) * 100}%` }} />
        <span className="battle-seg fl" style={{ width: `${(fl / total) * 100}%` }} />
      </div>
      <div className="battle-legend">
        <span><i className="dot src-oscar" /> Oscar tighter <b>{os}</b>
          {r.substantial[OS] ? <span className="dim"> ({r.substantial[OS]} substantial)</span> : null}</span>
        <span><i className="dot src-other" /> comparable <b>{even}</b></span>
        <span><i className="dot src-bcbsfl" /> Florida Blue tighter <b>{fl}</b>
          {r.substantial[FL] ? <span className="dim"> ({r.substantial[FL]} substantial)</span> : null}</span>
      </div>
    </div>
  );
}

function AddLeaderboard({ title, cls, items }: { title: string; cls: string; items: Tally[] }) {
  const max = Math.max(...items.map((i) => i.n), 1);
  return (
    <div className="lb">
      <div className="lb-head">
        <span className={`src-chip ${cls}`}>{title}</span> most often adds…
      </div>
      {items.length === 0 ? (
        <p className="solo-empty">No extra requirements recorded.</p>
      ) : (
        <div className="lb-rows">
          {items.map((it) => (
            <div className="lb-row" key={it.label}>
              <span className="lb-label" title={it.label}>{it.label}</span>
              <span className="lb-track">
                <span className={`lb-fill ${cls}`} style={{ width: `${(it.n / max) * 100}%` }} />
              </span>
              <span className="lb-n">{it.n}</span>
            </div>
          ))}
        </div>
      )}
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
              {open && <ComparisonView c={c} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GapColumns({ a }: { a: Analysis }) {
  return (
    <div className="gap-cols">
      <GapColumn
        src="bcbsfl" has={FL} lacks={OS}
        items={a.gaps.bcbsfl} catCounts={a.summary.bcbsfl_gap_categories}
      />
      <GapColumn
        src="oscar" has={OS} lacks={FL}
        items={a.gaps.oscar} catCounts={a.summary.oscar_gap_categories}
      />
    </div>
  );
}

function GapColumn({
  src, has, lacks, items, catCounts,
}: {
  src: "bcbsfl" | "oscar"; has: string; lacks: string;
  items: Analysis["gaps"]["bcbsfl"]; catCounts: Record<string, number>;
}) {
  const [q, setQ] = useState("");
  const [all, setAll] = useState(false);
  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase();
    return n
      ? items.filter((g) => g.label.toLowerCase().includes(n) ||
          (g.description || "").toLowerCase().includes(n) ||
          g.category.toLowerCase().includes(n))
      : items;
  }, [items, q]);
  const shown = all ? filtered : filtered.slice(0, 12);

  return (
    <div className="gap-col">
      <div className="gap-colhead">
        <span className={`src-chip ${src === "bcbsfl" ? "src-bcbsfl" : "src-oscar"}`}>{has}</span>
        <span className="gap-colhead-text">has a policy · <strong>{lacks}</strong> doesn't</span>
      </div>
      <p className="gap-colsub">
        {items.length} dedicated guidelines with no {lacks} counterpart — a potential coverage
        gap (or an opportunity) for {lacks}.
      </p>
      <div className="gap-cats">
        {Object.entries(catCounts).slice(0, 6).map(([c, n]) => (
          <span key={c} className="gap-cat"><b>{n}</b> {c}</span>
        ))}
      </div>
      <input
        className="gap-search"
        placeholder={`Filter ${has}-only policies…`}
        value={q}
        onChange={(e) => { setQ(e.target.value); setAll(true); }}
      />
      <div className="gap-cards">
        {shown.map((g) => (
          <Link key={g.topic_id} to={`/topic/${g.topic_id}`} className="gap-card">
            <div className="gap-card-top">
              <span className="gap-card-name">{g.label}</span>
              {g.policy_id && <span className="mono dim">{g.policy_id}</span>}
            </div>
            {g.description && <p className="gap-card-desc">{g.description}</p>}
            <span className="gap-card-cat">{g.category}</span>
          </Link>
        ))}
      </div>
      {!all && filtered.length > shown.length && (
        <button className="gap-more" onClick={() => setAll(true)}>
          Show all {filtered.length} →
        </button>
      )}
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
