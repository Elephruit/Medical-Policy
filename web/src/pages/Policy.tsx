import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { loadText, useData } from "../data";
import type { PolicyText } from "../types";
import { SourceChip } from "../components/Bits";
import { Criteria } from "../components/Criteria";

export default function Policy() {
  const { id } = useParams();
  const { byId, topicById } = useData();
  const p = id ? byId.get(id) : undefined;
  const [text, setText] = useState<PolicyText | null>(null);

  useEffect(() => {
    if (id) loadText(id).then(setText);
  }, [id]);

  if (!p) return <div className="empty">Policy not found.</div>;
  const topic = p.topic_id != null ? topicById.get(p.topic_id) : undefined;

  return (
    <div className="detail">
      <div className="page-head">
        <div>
          <Link to="/browse" className="back">← Browse</Link>
          <h1>{p.title}</h1>
          <div className="detail-meta">
            <SourceChip source={p.source} />
            {p.policy_id && <span className="mono">{p.policy_id}</span>}
            {p.version && <span className="dim">v{p.version}</span>}
            {topic && topic.cross_payer && (
              <Link to={`/topic/${topic.topic_id}`} className="pill-link">
                Compare across payers →
              </Link>
            )}
          </div>
        </div>
      </div>

      <div className="detail-cols">
        <aside className="detail-side">
          <Info label="Payer" value={p.sourceLabel} />
          <Info label="Category" value={p.category} />
          <Info label="Effective" value={p.effective_date} />
          <Info label="Revised" value={p.revised_date} />
          <Info label="Pages" value={p.page_count?.toString()} />
          {p.source_url && (
            <a className="btn" href={p.source_url} target="_blank" rel="noreferrer">
              View original source ↗
            </a>
          )}
          {text && text.codes.length > 0 && (
            <div className="codes">
              <div className="info-label">Procedure codes ({text.codes.length})</div>
              <div className="code-chips">
                {text.codes.slice(0, 80).map((c) => (
                  <span key={c} className="code-chip">{c}</span>
                ))}
              </div>
            </div>
          )}
        </aside>

        <article className="detail-text">
          {text ? (
            <Criteria text={text.full_text} emptyLabel="No text extracted." />
          ) : (
            <div className="muted">Loading full text…</div>
          )}
        </article>
      </div>
    </div>
  );
}

function Info({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="info">
      <span className="info-label">{label}</span>
      <span className="info-value">{value || "—"}</span>
    </div>
  );
}
