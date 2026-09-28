import { getParticipantId } from "./api";

export interface SurveyDraft {
  ideas: string[];
  deadline: number;
  sessionId: string;
  requestId: string;
}

const key = (itemId: string) => `aut:draft:v1:${getParticipantId()}:${itemId}`;

export function readDraft(itemId: string): SurveyDraft | null {
  try {
    const value = JSON.parse(localStorage.getItem(key(itemId)) || "null");
    return value && Array.isArray(value.ideas) && value.ideas.length === 10 &&
      value.ideas.every((idea: unknown) => typeof idea === "string") &&
      typeof value.deadline === "number" && typeof value.sessionId === "string" &&
      typeof value.requestId === "string" ? value : null;
  } catch { return null; }
}

export function saveDraft(itemId: string, draft: SurveyDraft) {
  try { localStorage.setItem(key(itemId), JSON.stringify(draft)); return true; }
  catch { return false; }
}

export function clearDraft(itemId: string) {
  try { localStorage.removeItem(key(itemId)); } catch { /* Bộ nhớ trình duyệt có thể bị khóa. */ }
}
