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
