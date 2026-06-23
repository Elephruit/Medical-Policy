export interface Policy {
  id: string;
  source: string;
  sourceLabel: string;
  policy_id: string | null;
  version: string | null;
  title: string;
  category: string | null;
  effective_date: string | null;
  revised_date: string | null;
  page_count: number | null;
  n_codes: number;
  source_url: string | null;
  topic_id: number | null;
}

export interface Topic {
  topic_id: number;
  label: string;
  size: number;
  sources: string[];
  cross_payer: boolean;
  members: string[];
  score: number;
  llm_matched?: boolean;
}

export interface PolicyText {
  id: string;
  title: string;
  codes: string[];
  excerpt: string;
  full_text: string;
}

export interface Meta {
  policy_count: number;
  topic_count: number;
  cross_payer_topics: number;
  sources: { slug: string; label: string; count: number }[];
}

export interface Side {
  id: string;
  policy_id: string | null;
  title: string;
  version: string | null;
  effective_date: string | null;
  revised_date: string | null;
  page_count: number | null;
  signals: Record<string, boolean>;
  excerpt: string;
  consolidated_into: string | null;
}

export interface AlignedCriterion {
  category: string;
  florida_blue: string;
  oscar: string;
  agreement: "same" | "differs";
}
export interface SoloCriterion {
  category: string;
  detail: string;
}
export interface Restrictiveness {
  more_restrictive: "Florida Blue" | "Oscar" | "neither";
  magnitude: "none" | "minor" | "moderate" | "substantial";
  rationale: string;
  cost_note: string;
}
export interface LlmComparison {
  summary: string;
  shared: AlignedCriterion[];
  florida_blue_only: SoloCriterion[];
  oscar_only: SoloCriterion[];
  restrictiveness?: Restrictiveness;
}

export interface Comparison {
  topic_id: number;
  label: string;
  score: number;
  category: string;
  bcbsfl: Side;
  oscar: Side;
  diffs: { key: string; label: string; only: string }[];
  llm?: LlmComparison | null;
  llm_matched?: boolean;
}

export interface Finding {
  id: string;
  type: "criteria" | "organization" | "gap" | "agreement";
  tier: "major" | "notable";
  title: string;
  summary: string;
  detail: string;
  examples: { topic_id: number; label: string }[];
}

export interface GapItem {
  topic_id: number;
  id?: string;
  label: string;
  policy_id: string | null;
  category: string;
  description?: string;
}

export interface DrugRef {
  policy_id: string;
  title: string;
  doc_key: string;
  id: string;
}
export interface DrugMember {
  drug: string;
  generic: string;
  bcbsfl: DrugRef | null;
  oscar_perdrug: DrugRef | null;
}
export interface DrugFamily {
  oscar_class: { policy_id: string; title: string; full_title: string; doc_key: string; version: string | null; id: string };
  n_listed: number;
  n_matched_bcbsfl: number;
  members: DrugMember[];
}

export interface Analysis {
  summary: {
    total_policies: number;
    by_source: Record<string, number>;
    cross_payer_topics: number;
    bcbsfl_only: number;
    oscar_only: number;
    topics_with_diffs: number;
    diff_type_counts: Record<string, number>;
    bcbsfl_gap_categories: Record<string, number>;
    oscar_gap_categories: Record<string, number>;
    llm_matched_topics?: number;
    restrictiveness?: {
      scored: number;
      by_payer: Record<string, number>;
      substantial: Record<string, number>;
    } | null;
    source_labels: Record<string, string>;
  };
  findings: Finding[];
  comparisons: Comparison[];
  gaps: { bcbsfl: GapItem[]; oscar: GapItem[] };
}
