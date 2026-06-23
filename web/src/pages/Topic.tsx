import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadAnalysis, loadText, useData } from "../data";
import type { Comparison, PolicyText } from "../types";
import { SourceChip } from "../components/Bits";
import { ComparisonView } from "../components/Comparison";

export default function Topic() {
  const { id } = useParams();
  const { topicById, byId } = useData();
  const topic = topicById.get(Number(id));
  const [texts, setTexts] = useState<Record<string, PolicyText>>({});
  const [cmp, setCmp] = useState<Comparison | null>(null);

  useEffect(() => {
    let live = true;
    loadAnalysis().then((a) => {
      if (live) setCmp(a.comparisons.find((c) => c.topic_id === Number(id)) || null);
    });
    return () => { live = false; };
  }, [id]);

  const members = useMemo(
    () => (topic ? topic.members.map((m) => byId.get(m)!).filter(Boolean) : []),
    [topic, byId]
  );

  useEffect(() => {
    let live = true;
    Promise.all(members.map((p) => loadText(p.id))).then((list) => {
      if (!live) return;
      const map: Record<string, PolicyText> = {};
      list.forEach((t) => (map[t.id] = t));
      setTexts(map);
    });
    return () => {
      live = false;
    };
  }, [members]);

  if (!topic) return <div className="empty">Topic not found.</div>;

  // group members by payer -> columns
  const bySource = new Map<string, typeof members>();
  for (const p of members) {
    if (!bySource.has(p.source)) bySource.set(p.source, []);
    bySource.get(p.source)!.push(p);
  }
  const columns = [...bySource.entries()];

  return (
    <div>
      <div className="page-head">
        <div>
          <Link to="/" className="back">← All topics</Link>
          <h1>{topic.label}</h1>
          <p className="sub">
            {topic.cross_payer
              ? `Compared across ${topic.sources.length} payers`
              : "Single-payer topic"}{" "}
            · {topic.size} policies
            {cmp?.llm_matched && <span className="ai-badge" title="Matched by AI subject normalization">AI-matched</span>}
          </p>
        </div>
      </div>

      {cmp && (
        <section className="topic-analysis">
          <h2 className="topic-analysis-h">Coverage comparison</h2>
          <ComparisonView c={cmp} />
        </section>
      )}

      <h2 className="topic-analysis-h">Each payer's policy</h2>
      <div className="compare-grid" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(280px, 1fr))` }}>
        {columns.map(([source, ps]) => (
          <div key={source} className="compare-col">
            <div className="compare-colhead">
              <SourceChip source={source} />
            </div>
            {ps.map((p) => {
              const t = texts[p.id];
              return (
                <div key={p.id} className="compare-card">
                  <Link to={`/policy/${p.id}`} className="cc-title">{p.title}</Link>
                  <div className="cc-rows">
                    <Field label="Policy #" value={p.policy_id} />
                    <Field label="Version" value={p.version} />
                    <Field label="Effective" value={p.effective_date} />
                    <Field label="Revised" value={p.revised_date} />
                    <Field label="Pages" value={p.page_count?.toString()} />
                    <Field label="Codes" value={t ? `${t.codes.length}` : "…"} />
                  </div>
                  <div className="cc-excerpt">
                    {t ? (t.excerpt || <span className="muted">No excerpt.</span>) : <span className="muted">Loading…</span>}
                  </div>
                  {p.source_url && (
                    <a className="cc-link" href={p.source_url} target="_blank" rel="noreferrer">
                      View source ↗
                    </a>
                  )}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      <span className="field-value">{value || "—"}</span>
    </div>
  );
}
