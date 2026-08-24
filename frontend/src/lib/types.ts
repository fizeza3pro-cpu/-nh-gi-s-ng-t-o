export interface Item {
  id: string;
  name: string;
  description: string;
  codes: string[];
}

export type IdeaStatus = "VALID" | "INVALID" | "DUPLICATE";

export interface MappedIdea {
  original: string;
  normalized: string;
  code: string;
  status: IdeaStatus;
  reason: string;
}

export interface MappingResult {
  ideas: MappedIdea[];
}

export interface PerIdeaScore {
  normalized: string;
  code: string;
  originality: number;
  elaboration: number;
  note: string;
}

export interface ScoringResult {
  fluency: number;
  flexibility: number;
  flexibility_codes: string[];
  originality: number;
  elaboration: number;
  per_idea_scores: PerIdeaScore[];
  summary_vi: string;
}

export interface ScoreResponse {
  response_id: string;
  item: Item;
  raw_input: string;
  mapping: MappingResult;
  scoring: ScoringResult;
}

export interface ResponseSummary {
  response_id: string;
  created_at: string;
  item_id: string;
  item_name: string;
  fluency: number;
  flexibility: number;
  originality: number;
  elaboration: number;
}

// --- Auth ---

export type UserRole = "user" | "admin";

export interface User {
  id: string;
  username: string;
  full_name: string;
  role: UserRole;
  created_at: string;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
}
