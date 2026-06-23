import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { loadAnalysis, loadDrugFamilies } from "../data";
import type { Analysis, Comparison, DrugFamily, Finding } from "../types";

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
        {rows.map((c) => (
          <div key={c.topic_id} className={`cmp ${openId === c.topic_id ? "open" : ""}`}>
            <button className="cmp-head" onClick={() => setOpenId(openId === c.topic_id ? null : c.topic_id)}>
              <span className="cmp-label">{c.label}</span>
              <span className="cmp-cat">{c.category}</span>
              <span className="cmp-diffs">
                {c.diffs.length === 0
                  ? <span className="agree">criteria aligned</span>
                  : c.diffs.map((d) => (
                      <span key={d.key} className={`dtag ${d.only === FL ? "dtag-fl" : "dtag-os"}`}>
                        {d.label}: {d.only}
                      </span>
                    ))}
              </span>
              <span className="cmp-caret">{openId === c.topic_id ? "−" : "+"}</span>
            </button>
            {openId === c.topic_id && (
              <div className="cmp-body">
                {(["bcbsfl", "oscar"] as const).map((src) => {
                  const side = c[src];
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
                      <p className="cmp-excerpt">{side.excerpt || "—"}</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
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

// Minimal inline markdown: **bold**, *italic*, `code`.
function mdInline(t: string): string {
  return t
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}
