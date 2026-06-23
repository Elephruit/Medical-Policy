import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useData } from "../data";
import { SourceChip, ScoreBadge } from "../components/Bits";

export default function Compare() {
  const { topics } = useData();
  const [q, setQ] = useState("");
  const [crossOnly, setCrossOnly] = useState(true);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return topics
      .filter((t) => (crossOnly ? t.cross_payer : true))
      .filter((t) => (needle ? t.label.toLowerCase().includes(needle) : true))
      .sort((a, b) =>
        b.cross_payer === a.cross_payer
          ? b.size - a.size || b.score - a.score
          : Number(b.cross_payer) - Number(a.cross_payer)
      )
      .slice(0, 400);
  }, [topics, q, crossOnly]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1>Compare policies across payers</h1>
          <p className="sub">
            Topics group equivalent policies from different payers. Open one to
            see them side by side.
          </p>
        </div>
      </div>

      <div className="toolbar">
        <input
          className="search"
          placeholder="Search topics (e.g. glucose, bariatric, dupilumab)…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <label className="toggle">
          <input
            type="checkbox"
            checked={crossOnly}
            onChange={(e) => setCrossOnly(e.target.checked)}
          />
          Cross-payer only
        </label>
      </div>

      <div className="topic-list">
        {rows.map((t) => (
          <Link key={t.topic_id} to={`/topic/${t.topic_id}`} className="topic-row">
            <div className="topic-main">
              <span className="topic-label">{t.label}</span>
              <span className="topic-meta">{t.size} policies</span>
            </div>
            <div className="topic-side">
              {t.sources.map((s) => (
                <SourceChip key={s} source={s} />
              ))}
              {t.cross_payer && <ScoreBadge score={t.score} />}
            </div>
          </Link>
        ))}
        {rows.length === 0 && <div className="empty">No topics match “{q}”.</div>}
      </div>
    </div>
  );
}
