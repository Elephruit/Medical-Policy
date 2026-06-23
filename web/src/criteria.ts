// Clean PDF-extracted policy text and parse enumerated clinical criteria into a
// readable tree.
//
// Why: pypdf extracts some payer PDFs (notably Oscar's) with a line break after
// every single word, so raw text renders as one-word-per-line. And even when the
// whitespace is collapsed, clinical criteria are a dense run-on ("...met: 1. ...
// a. ... i. ... ii. ...") that's hard to scan. We collapse the whitespace, then
// re-derive structure from the enumeration markers the policies already use.

export interface CritItem {
  marker: string; // "1.", "a.", "i.", …
  text: string;
  depth: number; // 0 = top level
}

export interface ParsedCriteria {
  preamble: string; // text before the first marker (e.g. the "medically necessary when…" lead-in)
  items: CritItem[];
}

// Collapse every run of whitespace (incl. the pathological per-word newlines) to
// a single space. Structure is re-derived from markers, not from the original
// line breaks, which are unreliable.
export function cleanText(raw: string): string {
  return (raw || "").replace(/­/g, "").replace(/\s+/g, " ").trim();
}

// A marker is a short label + "." or ")" followed by a space and a word char.
// Requiring the trailing space is what keeps "e.g.", "i.e.", "U.S." from matching
// (they have no internal space), while "1. Symptoms" / "a. Chronic" do.
const MARKER_RE = /(?:^|\s)((?:\d{1,2}|[A-Za-z]{1,4})[.)])\s+(?=[A-Za-z0-9(“"'])/g;
const ROMAN_MULTI = /^(?:ii|iii|iv|vi|vii|viii|ix|xi|xii|xiii)$/;

type Style = "num" | "lower" | "upper" | "roman";

function styleOf(core: string): Style | null {
  if (/^\d{1,2}$/.test(core)) return "num";
  if (/^[a-z]$/.test(core)) return "lower"; // single letter; may be promoted to roman in context
  if (/^[A-Z]$/.test(core)) return "upper";
  if (ROMAN_MULTI.test(core.toLowerCase())) return "roman";
  return null; // multi-char non-roman (e.g. a stray "and.") — not a list marker
}

export function parseCriteria(raw: string): ParsedCriteria {
  const text = cleanText(raw);
  if (!text) return { preamble: "", items: [] };

  // Collect candidate markers with their positions.
  const hits: { label: string; core: string; start: number; textStart: number }[] = [];
  for (let m; (m = MARKER_RE.exec(text)); ) {
    const label = m[1];
    const core = label.slice(0, -1);
    if (!styleOf(core)) continue;
    const labelStart = m.index + m[0].indexOf(label);
    hits.push({ label, core, start: labelStart, textStart: labelStart + label.length });
  }

  if (hits.length === 0) return { preamble: text, items: [] };

  const preamble = text.slice(0, hits[0].start).trim();
  const items: CritItem[] = [];
  const stack: Style[] = [];

  hits.forEach((h, i) => {
    const end = i + 1 < hits.length ? hits[i + 1].start : text.length;
    let body = text.slice(h.textStart, end).trim();
    // Drop trailing connectors that belong to the structure, not the prose.
    body = body.replace(/[;,]?\s*(and|or)\s*$/i, "").trim();

    let style = styleOf(h.core)!;
    // "i"/"v"/"x" look like letters but are roman sub-items when a letter level
    // is already open (… a. … b. … i. …).
    if (style === "lower" && /^[ivx]$/.test(h.core) && stack.includes("lower")) {
      style = "roman";
    }

    let depth: number;
    const at = stack.indexOf(style);
    if (at >= 0) {
      depth = at;
      stack.length = at + 1; // sibling: pop deeper levels
    } else {
      stack.push(style);
      depth = stack.length - 1; // new style nests one level deeper
    }

    if (body) items.push({ marker: h.label, text: body, depth });
  });

  return { preamble, items };
}

// --- conservative similarity, for the side-by-side comparison ---------------

const STOP = new Set(
  ("the a an and or of to in for with on at is are be when met meets all any one " +
    "following criteria member patient must has have had not no as if that this " +
    "least which who may been being than then per each both either").split(" ")
);

function terms(s: string): Set<string> {
  const out = new Set<string>();
  for (const w of s.toLowerCase().match(/[a-z][a-z-]{3,}/g) || []) {
    if (!STOP.has(w)) out.add(w);
  }
  return out;
}

// Returns the indices on `b` that share substantial wording with each `a` item.
// Used only to tint shared vs. unique criteria — intentionally strict so a tint
// of "shared" is trustworthy; borderline items stay "unique".
export function markShared(a: CritItem[], b: CritItem[]): boolean[] {
  const bTerms = b.map((it) => terms(it.text));
  return a.map((it) => {
    const at = terms(it.text);
    if (at.size < 2) return false;
    return bTerms.some((bt) => {
      let inter = 0;
      for (const w of at) if (bt.has(w)) inter++;
      const union = at.size + bt.size - inter;
      return inter >= 3 || (union > 0 && inter / union >= 0.4);
    });
  });
}
