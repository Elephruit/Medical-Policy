const SOURCE_META: Record<string, { label: string; cls: string }> = {
  bcbsfl: { label: "BCBS Florida", cls: "src-bcbsfl" },
  oscar: { label: "Oscar Health", cls: "src-oscar" },
};

export function SourceChip({ source }: { source: string }) {
  const m = SOURCE_META[source] || { label: source, cls: "src-other" };
  return <span className={`src-chip ${m.cls}`}>{m.label}</span>;
}

export function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const tier = score >= 0.85 ? "hi" : score >= 0.6 ? "mid" : "lo";
  return (
    <span className={`score score-${tier}`} title="Match confidence">
      {pct}% match
    </span>
  );
}

// How a cross-payer topic was matched: by the LLM subject-normalization pass, or
// by the deterministic title/text-similarity matcher.
export function MatchBadge({ crossPayer, llmMatched }: { crossPayer: boolean; llmMatched?: boolean }) {
  if (!crossPayer) return null;
  return llmMatched ? (
    <span className="match-badge ai" title="Matched by AI subject normalization — the title matcher missed this one">
      AI-matched
    </span>
  ) : (
    <span className="match-badge code" title="Matched by deterministic title/text similarity">
      Code-matched
    </span>
  );
}
