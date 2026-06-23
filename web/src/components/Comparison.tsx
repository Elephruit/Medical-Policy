import { Link } from "react-router-dom";
import type { Comparison, LlmComparison } from "../types";
import { Criteria } from "./Criteria";

const FL = "Florida Blue";
const OS = "Oscar";

// The coverage requirements we track and align side-by-side (regex fallback).
const REQUIREMENTS: { key: string; label: string }[] = [
  { key: "prior_auth", label: "Prior authorization" },
  { key: "step_therapy", label: "Step therapy (try & fail first)" },
  { key: "age_limit", label: "Age restriction" },
  { key: "specialist", label: "Specialist prescriber" },
  { key: "quantity", label: "Quantity / dose limit" },
  { key: "experimental", label: "Some uses experimental / investigational" },
];

export function diffCount(c: Comparison): number {
  if (c.llm) {
    return (
      c.llm.florida_blue_only.length +
      c.llm.oscar_only.length +
      c.llm.shared.filter((s) => s.agreement === "differs").length
    );
  }
  return c.diffs.length;
}

// Compact one-line "who's tighter" chip for list rows and headers.
export function RestrictivenessChip({ c }: { c: Comparison }) {
  const r = c.llm?.restrictiveness;
  if (!r || r.more_restrictive === "neither" || r.magnitude === "none") return null;
  const cls = r.more_restrictive === FL ? "src-bcbsfl" : "src-oscar";
  return (
    <span className={`restr-chip ${cls}`} title={r.rationale}>
      {r.more_restrictive} tighter
    </span>
  );
}

// The full comparison body: LLM-aligned view (or regex fallback) + source text.
export function ComparisonView({ c }: { c: Comparison }) {
  return (
    <div className="cmp-body">
      {c.llm ? <LlmView llm={c.llm} /> : <HeuristicView c={c} />}

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
          <SoloColumn title={FL} cls="src-bcbsfl" items={flOnly}
            empty="Nothing required here that Oscar doesn't also require." />
          <SoloColumn title={OS} cls="src-oscar" items={osOnly}
            empty="Nothing required here that Florida Blue doesn't also require." />
        </div>
      )}

      {shared.length > 0 && (
        <div className="llm-shared">
          <div className="llm-shared-head">
            <h4>Requirements both payers share</h4>
            <span className="llm-shared-sub">
              {differing > 0 ? `${differing} of ${shared.length} differ in the specifics` : "specifics align"}
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
