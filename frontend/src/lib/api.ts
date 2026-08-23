import type { Item, ResponseSummary, ScoreResponse } from "@/lib/types";

const BASE = "/api";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let message = `Lỗi máy chủ (${res.status})`;
    try {
      const data = JSON.parse(text);
      if (data?.detail) message = data.detail;
    } catch {
      if (text) message = text;
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => fetch(`${BASE}/health`).then(handle<{ status: string; model: string }>),
  listItems: () => fetch(`${BASE}/items`).then(handle<Item[]>),
  getItem: (id: string) => fetch(`${BASE}/items/${id}`).then(handle<Item>),
  score: (itemId: string, rawInput: string) =>
    fetch(`${BASE}/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ item_id: itemId, raw_input: rawInput }),
    }).then(handle<ScoreResponse>),
  listResponses: () => fetch(`${BASE}/responses`).then(handle<ResponseSummary[]>),
  getResponse: (id: string) =>
    fetch(`${BASE}/responses/${id}`).then(handle<ScoreResponse>),
};

const SESSION_KEY = "aut:last-response";

export function cacheResponse(resp: ScoreResponse) {
  try {
    sessionStorage.setItem(`${SESSION_KEY}:${resp.response_id}`, JSON.stringify(resp));
  } catch {
    /* ignore */
  }
}

export function readCachedResponse(id: string): ScoreResponse | null {
  try {
    const raw = sessionStorage.getItem(`${SESSION_KEY}:${id}`);
    return raw ? (JSON.parse(raw) as ScoreResponse) : null;
  } catch {
    return null;
  }
}
