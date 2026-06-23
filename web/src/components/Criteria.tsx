import { useMemo } from "react";
import { parseCriteria, markShared, type CritItem } from "../criteria";

// Render a policy's coverage criteria as a readable, indented outline.
// `compareTo` (the other payer's criteria text) enables shared/unique tinting.
export function Criteria({
  text,
  compareTo,
  emptyLabel = "—",
}: {
  text: string;
  compareTo?: string;
  emptyLabel?: string;
}) {
  const parsed = useMemo(() => parseCriteria(text), [text]);
  const shared = useMemo(() => {
    if (!compareTo) return null;
    const other = parseCriteria(compareTo).items;
    return markShared(parsed.items, other);
  }, [parsed, compareTo]);

  if (!parsed.preamble && parsed.items.length === 0) {
    return <p className="crit-empty">{emptyLabel}</p>;
  }

  return (
    <div className="crit">
      {parsed.preamble && <p className="crit-lead">{parsed.preamble}</p>}
      {parsed.items.length > 0 && (
        <ul className="crit-list">
          {parsed.items.map((it, i) => (
            <Item key={i} it={it} tone={shared ? (shared[i] ? "shared" : "unique") : null} />
          ))}
        </ul>
      )}
    </div>
  );
}

function Item({ it, tone }: { it: CritItem; tone: "shared" | "unique" | null }) {
  return (
    <li
      className={`crit-item depth-${Math.min(it.depth, 3)} ${tone ? `crit-${tone}` : ""}`}
      style={{ marginLeft: Math.min(it.depth, 3) * 18 }}
    >
      <span className="crit-marker">{it.marker}</span>
      <span className="crit-text">{it.text}</span>
    </li>
  );
}
