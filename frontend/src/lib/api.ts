import type {
  AdminDashboardStats,
  AdminCuratorAudit,
  AdminExtractionAudit,
  AdminCodePatch,
  AdminCodebookSummary,
  AdminParticipantDetail,
  AdminParticipantSummary,
  AuthTokenResponse,
  Item,
  ParticipantIdentity,
  ParticipantIdentifyResult,
  ParticipantProfile,
  ResponseSummary,
  ScoreResponse,
  User,
} from "@/lib/types";

const BASE = "/api";
const TOKEN_KEY = "aut:token";
const PARTICIPANT_ID_KEY = "aut:participant-id";
const PARTICIPANT_PROFILE_KEY = "aut:participant-email-profile:v2";

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

export function getParticipantId(): string | null {
  return localStorage.getItem(PARTICIPANT_ID_KEY);
}

export function hasParticipantProfile(): boolean {
  return getParticipantIdentity() !== null;
}

export function getParticipantIdentity(): ParticipantIdentity | null {
  const participantId = getParticipantId();
  const raw = localStorage.getItem(PARTICIPANT_PROFILE_KEY);
  if (!participantId || !raw) return null;
  try {
    const participant = JSON.parse(raw) as ParticipantIdentity;
    return participant.id === participantId ? participant : null;
  } catch {
    return null;
  }
}

export function clearParticipantProfile(): void {
  localStorage.removeItem(PARTICIPANT_PROFILE_KEY);
  localStorage.removeItem(PARTICIPANT_ID_KEY);
}

function rememberParticipant<T extends { id: string }>(participant: T): T {
  localStorage.setItem(PARTICIPANT_ID_KEY, participant.id);
  localStorage.setItem(PARTICIPANT_PROFILE_KEY, JSON.stringify(participant));
  return participant;
}

function participantHeaders(extra?: Record<string, string>): Record<string, string> {
  const participantId = getParticipantId();
  return {
    ...extra,
    ...(participantId ? { "X-Participant-Id": participantId } : {}),
  };
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

  // --- Auth chỉ dành cho admin ---
  login: (username: string, password: string) =>
    fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }).then(handle<AuthTokenResponse>),

  me: () =>
    fetch(`${BASE}/auth/me`, { headers: authHeaders() }).then(handle<User>),

  // --- Khảo sát công khai ---
  listItems: () => fetch(`${BASE}/items`).then(handle<Item[]>),

  getItem: (id: string) => fetch(`${BASE}/items/${id}`).then(handle<Item>),

  identifyParticipant: async (email: string) => {
    const participantId = getParticipantId();
    const result = await fetch(`${BASE}/participants/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        ...(participantId ? { participant_id: participantId } : {}),
      }),
    }).then(handle<ParticipantIdentifyResult>);
    if (result.participant) rememberParticipant(result.participant);
    return result;
  },

  createParticipant: async (email: string, profile: ParticipantProfile) => {
    const participant = await fetch(`${BASE}/participants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, ...profile }),
    }).then(handle<ParticipantIdentity>);
    return rememberParticipant(participant);
  },

  score: (itemId: string, rawInput: string) =>
    fetch(`${BASE}/score`, {
      method: "POST",
      headers: participantHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ item_id: itemId, raw_input: rawInput }),
    }).then(handle<ScoreResponse>),

  listResponses: () =>
    fetch(`${BASE}/responses`, { headers: authHeaders() }).then(
      handle<ResponseSummary[]>,
    ),

  getResponse: (id: string) =>
    fetch(`${BASE}/responses/${id}`).then(handle<ScoreResponse>),

  // --- Admin (cần role admin, backend tự chặn 403 nếu không đủ quyền) ---
  adminDashboard: () =>
    fetch(`${BASE}/admin/dashboard`, { headers: authHeaders() }).then(
      handle<AdminDashboardStats>,
    ),

  adminListParticipants: () =>
    fetch(`${BASE}/admin/participants`, { headers: authHeaders() }).then(
      handle<AdminParticipantSummary[]>,
    ),

  adminParticipantDetail: (participantId: string) =>
    fetch(`${BASE}/admin/participants/${participantId}`, { headers: authHeaders() }).then(
      handle<AdminParticipantDetail>,
    ),

  adminListCodebooks: () =>
    fetch(`${BASE}/admin/items/codebooks`, { headers: authHeaders() }).then(
      handle<AdminCodebookSummary[]>,
    ),

  adminCodebook: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/codebook`, { headers: authHeaders() }).then(
      handle<AdminCodebookSummary>,
    ),

  adminExtractionAudit: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/extraction-audit`, {
      headers: authHeaders(),
    }).then(handle<AdminExtractionAudit>),

  adminCuratorAudit: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/curator-audit`, {
      headers: authHeaders(),
    }).then(handle<AdminCuratorAudit>),

  adminUpdateCode: (itemId: string, codeId: string, patch: AdminCodePatch) =>
    fetch(`${BASE}/admin/items/${itemId}/codes/${codeId}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(patch),
    }).then(handle<AdminCodebookSummary>),

  adminArchiveCode: (itemId: string, codeId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/codes/${codeId}/archive`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handle<AdminCodebookSummary>),

  adminRestoreCode: (itemId: string, codeId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/codes/${codeId}/restore`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handle<AdminCodebookSummary>),

  adminMergeCode: (itemId: string, codeId: string, targetCodeId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/codes/${codeId}/merge`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ target_code_id: targetCodeId }),
    }).then(handle<AdminCodebookSummary>),

  adminDeleteCode: (itemId: string, codeId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/codes/${codeId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then(handle<AdminCodebookSummary>),

  adminDeleteAllCodes: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/codes`, {
      method: "DELETE",
      headers: authHeaders(),
    }).then(handle<AdminCodebookSummary>),

  adminReprocessItem: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/reprocess`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handle<{ processed: number }>),

  adminRemapItem: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/remap`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handle<{ processed: number }>),
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
