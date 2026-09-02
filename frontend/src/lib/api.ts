import type {
  AuthTokenResponse,
  Item,
  ResponseSummary,
  ScoreResponse,
  User,
} from "@/lib/types";

const BASE = "/api";
const TOKEN_KEY = "aut:token";

// --- Quản lý token (localStorage) ---
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

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

// Tự động gắn "Authorization: Bearer <token>" nếu đã đăng nhập.
function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = getToken();
  return {
    ...extra,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export const api = {
  health: () =>
    fetch(`${BASE}/health`).then(handle<{ status: string; model: string }>),

  // --- Auth (không cần token) ---
  register: (username: string, password: string, fullName: string) =>
    fetch(`${BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, full_name: fullName }),
    }).then(handle<User>),

  login: (username: string, password: string) =>
    fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then(handle<AuthTokenResponse>),


  me: () =>
    fetch(`${BASE}/auth/me`, { headers: authHeaders() }).then(handle<User>),

  // --- Cần đăng nhập ---
  listItems: () =>
    fetch(`${BASE}/items`, { headers: authHeaders() }).then(handle<Item[]>),

  getItem: (id: string) =>
    fetch(`${BASE}/items/${id}`, { headers: authHeaders() }).then(handle<Item>),

  score: (itemId: string, rawInput: string) =>
    fetch(`${BASE}/score`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ item_id: itemId, raw_input: rawInput }),
    }).then(handle<ScoreResponse>),

  listResponses: () =>
    fetch(`${BASE}/responses`, { headers: authHeaders() }).then(
      handle<ResponseSummary[]>,
    ),

  getResponse: (id: string) =>
    fetch(`${BASE}/responses/${id}`, { headers: authHeaders() }).then(
      handle<ScoreResponse>,
    ),
};

const SESSION_KEY = "aut:last-response";

export function cacheResponse(resp: ScoreResponse) {
  try {
    sessionStorage.setItem(
      `${SESSION_KEY}:${resp.response_id}`,
      JSON.stringify(resp),
    );
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
