import { createContext, useContext } from "react";
import MiniSearch from "minisearch";
import type { Analysis, Meta, Policy, PolicyText, Topic } from "./types";

const BASE = import.meta.env.BASE_URL || "/";

export interface Dataset {
  policies: Policy[];
  byId: Map<string, Policy>;
  topics: Topic[];
  topicById: Map<number, Topic>;
  meta: Meta;
  search: MiniSearch<Policy>;
}

export async function loadDataset(): Promise<Dataset> {
  const [policies, topics, meta] = await Promise.all([
    fetch(`${BASE}data/index.json`).then((r) => r.json() as Promise<Policy[]>),
    fetch(`${BASE}data/topics.json`).then((r) => r.json() as Promise<Topic[]>),
    fetch(`${BASE}data/meta.json`).then((r) => r.json() as Promise<Meta>),
  ]);

  const search = new MiniSearch<Policy>({
    fields: ["title", "policy_id", "category", "sourceLabel"],
    storeFields: ["id"],
    searchOptions: { boost: { title: 3, policy_id: 2 }, prefix: true, fuzzy: 0.2 },
  });
  search.addAll(policies.map((p) => ({ ...p, policy_id: p.policy_id ?? "" })));

  return {
    policies,
    byId: new Map(policies.map((p) => [p.id, p])),
    topics,
    topicById: new Map(topics.map((t) => [t.topic_id, t])),
    meta,
    search,
  };
}

const textCache = new Map<string, Promise<PolicyText>>();
export function loadText(id: string): Promise<PolicyText> {
  if (!textCache.has(id)) {
    textCache.set(
      id,
      fetch(`${BASE}data/text/${id}.json`).then((r) => r.json() as Promise<PolicyText>)
    );
  }
  return textCache.get(id)!;
}

let analysisPromise: Promise<Analysis> | null = null;
export function loadAnalysis(): Promise<Analysis> {
  if (!analysisPromise) {
    analysisPromise = fetch(`${BASE}data/analysis.json`).then(
      (r) => r.json() as Promise<Analysis>
    );
  }
  return analysisPromise;
}

export const DataContext = createContext<Dataset | null>(null);
export const useData = (): Dataset => {
  const d = useContext(DataContext);
  if (!d) throw new Error("dataset not loaded");
  return d;
};
