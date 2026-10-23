import type {
  AdminDashboardStats,
  AdminCuratorAudit,
  AdminExtractionAudit,
  AdminCodebookOverview,
  AdminCodebookSummary,
  AdminMappingReviewList,
  AdminMappingReviewResolution,
  AdminMappingReviewResult,
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
import type { AdminResearchReport } from "@/lib/report-types";

const BASE = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
const TOKEN_KEY = "aut:token";
const PARTICIPANT_ID_KEY = "aut:participant-id";
const PARTICIPANT_PROFILE_KEY = "aut:participant-email-profile:v3";
export const PARTICIPANT_PROFILE_CHANGED = "aut:participant-profile-changed";

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
  return Boolean(getParticipantIdentity()?.access_token);
}

export function getParticipantIdentity(): ParticipantIdentity | null {
  const participantId = getParticipantId();
  const raw = localStorage.getItem(PARTICIPANT_PROFILE_KEY);
  if (!participantId || !raw) return null;
  try {
    const participant = JSON.parse(raw) as ParticipantIdentity;
    const hasAiGroup =
      participant.ai_usage_group === "LOW" ||
      participant.ai_usage_group === "HIGH";
    return participant.id === participantId && hasAiGroup ? participant : null;
  } catch {
    return null;
  }
}

export function clearParticipantProfile(): void {
  localStorage.removeItem(PARTICIPANT_PROFILE_KEY);
  localStorage.removeItem(PARTICIPANT_ID_KEY);
  window.dispatchEvent(new Event(PARTICIPANT_PROFILE_CHANGED));
}

function rememberParticipant<T extends { id: string }>(participant: T): T {
  localStorage.setItem(PARTICIPANT_ID_KEY, participant.id);
  localStorage.setItem(PARTICIPANT_PROFILE_KEY, JSON.stringify(participant));
  window.dispatchEvent(new Event(PARTICIPANT_PROFILE_CHANGED));
  return participant;
}

function participantHeaders(
  extra?: Record<string, string>,
): Record<string, string> {
  const participantId = getParticipantId();
  const token = getParticipantIdentity()?.access_token;
  return {
    ...extra,
    ...(participantId ? { "X-Participant-Id": participantId } : {}),
    ...(token ? { "X-Participant-Token": token } : {}),
  };
}

async function fetchSurvey(
  url: string,
  options?: RequestInit,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 30_000);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(
        "Chưa nhận được xác nhận từ máy chủ. Nội dung được giữ nguyên để thử lại.",
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let message = `Lỗi máy chủ (${res.status})`;
    let code: string | undefined;
    try {
      const data = JSON.parse(text);
      if (typeof data?.detail === "string") message = data.detail;
      else if (typeof data?.detail?.message === "string") {
        message = data.detail.message;
        code = data.detail.code;
      } else if (Array.isArray(data?.detail)) {
        message =
          "Thông tin gửi lên chưa hợp lệ. Vui lòng kiểm tra lại các trường đã nhập.";
      }
    } catch {
      if (text) message = text;
    }
    throw new ApiError(message, res.status, code);
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
  listItems: () => fetch(`${BASE}/items`).then(handle<Item[]>), // lấy list item từ be

  getItem: (id: string) => fetch(`${BASE}/items/${id}`).then(handle<Item>),

  identifyParticipant: async (email: string) => {
    const participantId = getParticipantId();
    const result = await fetch(`${BASE}/participants/identify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        access_token: getParticipantIdentity()?.access_token,
        ...(participantId ? { participant_id: participantId } : {}),
      }),
    }).then(handle<ParticipantIdentifyResult>);
    if (result.participant) rememberParticipant(result.participant);
    return result;
  },

  createParticipant: async (
    email: string,
    profile: ParticipantProfile,
    recoveryToken?: string,
  ) => {
    const participantId = getParticipantId();
    const participant = await fetch(`${BASE}/participants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email,
        ...profile,
        access_token: recoveryToken || getParticipantIdentity()?.access_token,
        ...(participantId ? { participant_id: participantId } : {}),
      }),
    }).then(handle<ParticipantIdentity>);
    return rememberParticipant(participant);
  },

  adminIssueParticipantToken: (participantId: string) =>
    fetch(`${BASE}/admin/participants/${participantId}/access-token`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handle<ParticipantIdentity>),

  startSurveySession: (itemId: string) =>
    fetchSurvey(`${BASE}/survey-sessions`, {
      method: "POST",
      headers: participantHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ item_id: itemId, consent: true }),
    }).then(
      handle<{
        id: string;
        started_at: string;
        deadline_at: string;
        server_now: string;
      }>,
    ),

  score: (
    itemId: string,
    responses: string[],
    requestId: string,
    sessionId?: string,
  ) =>
    fetchSurvey(`${BASE}/score`, {
      method: "POST",
      headers: participantHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({
        item_id: itemId,
        responses,
        request_id: requestId,
        survey_session_id: sessionId,
      }),
    }).then(handle<ScoreResponse>),

  listResponses: () =>
    fetch(`${BASE}/responses`, { headers: authHeaders() }).then(
      handle<ResponseSummary[]>,
    ),

  getResponse: (id: string) =>
    fetchSurvey(`${BASE}/responses/${id}`, {
      headers: participantHeaders(),
    }).then(handle<ScoreResponse>),

  adminGetResponse: (id: string) =>
    fetch(`${BASE}/admin/responses/${id}`, { headers: authHeaders() }).then(
      handle<ScoreResponse>,
    ),

  adminRetryResponse: (id: string) =>
    fetch(`${BASE}/admin/responses/${id}/retry`, {
      method: "POST",
      headers: authHeaders(),
    }).then(handle<{ response_id: string; processing_state: string }>),

  participantResponses: () =>
    fetch(`${BASE}/participants/me/responses`, {
      headers: participantHeaders(),
    }).then(handle<ResponseSummary[]>),

  // --- Admin (cần role admin, backend tự chặn 403 nếu không đủ quyền) ---
  adminResearchReport: (
    options: {
      source?: string;
      itemId?: string;
      itemIds?: string[];
      signal?: AbortSignal;
    } = {},
  ) => {
    const query = new URLSearchParams();
    if (options.source) query.set("data_source", options.source);
    if (options.itemId) query.set("item_id", options.itemId);
    options.itemIds?.forEach((id) => query.append("item_ids", id));
    return fetch(`${BASE}/admin/reports/research?${query}`, {
      headers: authHeaders(),
      signal: options.signal,
    }).then(handle<AdminResearchReport>);
  },

  adminDashboard: () =>
    fetch(`${BASE}/admin/dashboard`, { headers: authHeaders() }).then(
      handle<AdminDashboardStats>,
    ),

  adminDownloadResponsesCsv: async (format: "csv" | "json" = "csv") => {
    const response = await fetch(
      `${BASE}/admin/exports/${format === "json" ? "analysis.json" : "responses.csv"}`,
      {
        headers: authHeaders(),
      },
    );
    if (!response.ok) {
      let message = `Lỗi ${response.status}`;
      try {
        const body = (await response.json()) as { detail?: string };
        message = body.detail || message;
      } catch {
        // Phản hồi lỗi không phải JSON.
      }
      throw new Error(message);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `aut-ket-qua-${new Date().toISOString().slice(0, 10)}.${format}`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  adminPipelineAudits: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/pipeline-audits`, {
      headers: authHeaders(),
    }).then(
      handle<
        Array<{
          id: string;
          event: string;
          created_at: string;
          payload: Record<string, unknown>;
        }>
      >,
    ),

  adminListParticipants: () =>
    fetch(`${BASE}/admin/participants`, { headers: authHeaders() }).then(
      handle<AdminParticipantSummary[]>,
    ),

  adminParticipantDetail: (participantId: string) =>
    fetch(`${BASE}/admin/participants/${participantId}`, {
      headers: authHeaders(),
    }).then(handle<AdminParticipantDetail>),

  adminListCodebooks: () =>
    fetch(`${BASE}/admin/items/codebooks`, { headers: authHeaders() }).then(
      handle<AdminCodebookOverview[]>,
    ),

  adminCodebook: (
    itemId: string,
    page = 1,
    pageSize = 20,
    codeFilter: "ALL" | "ACCEPTED" | "UNCERTAIN" | "REJECTED" = "ALL",
  ) => {
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      code_filter: codeFilter,
    });
    return fetch(`${BASE}/admin/items/${itemId}/codebook?${params}`, {
      headers: authHeaders(),
    }).then(handle<AdminCodebookSummary>);
  },

  adminExtractionAudit: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/extraction-audit`, {
      headers: authHeaders(),
    }).then(handle<AdminExtractionAudit>),

  adminCuratorAudit: (itemId: string) =>
    fetch(`${BASE}/admin/items/${itemId}/curator-audit`, {
      headers: authHeaders(),
    }).then(handle<AdminCuratorAudit>),

  adminMappingReviews: (itemId: string) =>
    fetch(
      `${BASE}/admin/items/${itemId}/mapping-reviews?review_status=PENDING`,
      {
        headers: authHeaders(),
      },
    ).then(handle<AdminMappingReviewList>),

  adminResolveMappingReview: (
    itemId: string,
    ideaId: string,
    payload: AdminMappingReviewResolution,
  ) =>
    fetch(`${BASE}/admin/items/${itemId}/mapping-reviews/${ideaId}/resolve`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    }).then(handle<AdminMappingReviewResult>),
};
