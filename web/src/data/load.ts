import { DataError, parseModelCard, parseSiteIndex } from "./parse";
import type { ModelCard, SiteIndex } from "./types";

type Fetcher = (url: string) => Promise<Response>;

async function fetchJson(url: string, fetcher: Fetcher): Promise<unknown> {
  const response = await fetcher(url);
  if (!response.ok) throw new DataError(`${url}: server answered ${response.status}`);
  return response.json();
}

export async function loadIndex(fetcher: Fetcher = fetch): Promise<SiteIndex> {
  return parseSiteIndex(await fetchJson("/data/index.json", fetcher));
}

export async function loadCard(modelId: string, fetcher: Fetcher = fetch): Promise<ModelCard> {
  return parseModelCard(await fetchJson(`/data/models/${encodeURIComponent(modelId)}.json`, fetcher));
}
