import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useData } from "../data";
import { SourceChip } from "../components/Bits";

export default function Browse() {
  const { policies, search, byId } = useData();
  const [q, setQ] = useState("");
  const [source, setSource] = useState("all");

  const results = useMemo(() => {
    let list = policies;
    const needle = q.trim();
    if (needle) {
      const hits = search.search(needle);
      const order = new Map(hits.map((h, i) => [h.id as string, i]));
      list = hits.map((h) => byId.get(h.id as string)!).filter(Boolean);
      list.sort((a, b) => (order.get(a.id)! - order.get(b.id)!));
    }
    if (source !== "all") list = list.filter((p) => p.source === source);
    return list.slice(0, 500);
  }, [policies, search, byId, q, source]);

  const sources = useMemo(
    () => [...new Set(policies.map((p) => p.source))],
    [policies]
  );

  return (
    <div>
      <div className="page-head">
        <h1>Browse all policies</h1>
      </div>
      <div className="toolbar">
        <input
          className="search"
          placeholder="Full-text search title, policy #, category…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          autoFocus
        />
        <select value={source} onChange={(e) => setSource(e.target.value)} className="select">
          <option value="all">All payers</option>
          {sources.map((s) => (
            <option key={s} value={s}>
              {byId.size && policies.find((p) => p.source === s)?.sourceLabel}
            </option>
          ))}
        </select>
        <span className="count">{results.length} shown</span>
      </div>

      <table className="grid">
        <thead>
          <tr>
            <th>Title</th>
            <th>Payer</th>
            <th>Policy #</th>
            <th>Category</th>
            <th>Revised</th>
            <th>Pages</th>
          </tr>
        </thead>
        <tbody>
          {results.map((p) => (
            <tr key={p.id}>
              <td><Link to={`/policy/${p.id}`} className="rowlink">{p.title}</Link></td>
              <td><SourceChip source={p.source} /></td>
              <td className="mono">{p.policy_id || "—"}</td>
              <td className="dim">{(p.category || "").replace(/^.*> /, "") || "—"}</td>
              <td className="mono dim">{p.revised_date || "—"}</td>
              <td className="dim">{p.page_count || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
