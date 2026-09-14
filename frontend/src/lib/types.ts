export interface Item {
  id: string;
  name: string;
  description: string;
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
  scoring: ScoringResult | null;
  scoring_status:
    | "COLLECTING"
    | "PENDING_REVIEW"
    | "PROVISIONAL"
    | "FINAL"
    | "EXCLUDED";
  codebook_version_id: string | null;
  status_message: string;
}

export type ParticipantGender =
  | "male"
  | "female"
  | "other"
  | "prefer_not_to_say";

export interface ParticipantProfile {
  full_name: string;
  age: number;
  gender: ParticipantGender;
  occupation: string;
}

export interface Participant extends ParticipantProfile {
  id: string;
  email_masked: string | null;
  email_verified_at: string | null;
  created_at: string;
}

export interface ParticipantIdentity {
  id: string;
  full_name: string | null;
  email_masked: string | null;
  email_verified_at: string | null;
}

export interface ParticipantIdentifyResult {
  profile_required: boolean;
  participant: ParticipantIdentity | null;
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
  scoring_status: string;
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

// --- Admin ---

export interface AdminItemBreakdown {
  item_id: string;
  item_name: string;
  response_count: number;
  calibration_status: string;
  qualifying_response_count: number;
  qualifying_participant_count: number;
  scoring_min_participants: number;
  scoring_min_responses: number;
  accepted_code_count: number;
  uncertain_code_count: number;
  rejected_code_count: number;
  active_version: number | null;
}

export interface AdminDailyStat {
  date: string;
  count: number;
}

export interface AdminScoringStatusCounts {
  collecting: number;
  pending_review: number;
  provisional: number;
  final: number;
  excluded: number;
}

export interface AdminDashboardStats {
  total_participants: number;
  total_responses: number;
  qualifying_response_count: number;
  responses_last_7_days: number;
  responses_previous_7_days: number;
  accepted_code_count: number;
  uncertain_code_count: number;
  rejected_code_count: number;
  scoring_status_counts: AdminScoringStatusCounts;
  daily_stats: AdminDailyStat[];
  by_item: AdminItemBreakdown[];
  recent_responses: AdminRecentResponse[];
}

export interface AdminParticipantSummary {
  id: string;
  full_name: string | null;
  email_masked: string | null;
  email_verified_at: string | null;
  age: number | null;
  gender: string | null;
  occupation: string | null;
  created_at: string;
  response_count: number;
  last_submitted_at: string | null;
}

export interface AdminParticipantDetail {
  participant: Omit<Participant, "age" | "gender" | "occupation"> & {
    age: number | null;
    gender: string | null;
    occupation: string | null;
  };
  responses: ResponseSummary[];
}

export interface AdminRecentResponse extends ResponseSummary {
  participant_id: string;
}

export interface AdminCodebookCode {
  id: string;
  name: string;
  description: string;
  validation_status: "ACCEPTED" | "UNCERTAIN" | "REJECTED";
  maturity_status: "EMERGING" | "STABLE" | "MERGED" | "ARCHIVED";
  confidence: number;
  relevance_reason: string;
  rejection_reason: string;
  created_by: string;
  admin_locked: boolean;
  merged_into_id: string | null;
  response_count: number;
  participant_count: number;
  idea_count: number;
  contributing_response_count: number;
  contributing_participant_count: number;
  contributing_idea_count: number;
  frequency: number;
  created_at: string;
}

export interface AdminExtractionExcludedIdea {
  idea_id: string;
  response_id: string;
  participant_id: string;
  original: string;
  normalized: string;
  status: "INVALID" | "DUPLICATE";
  reason: string;
  created_at: string;
}

export interface AdminExtractionAudit {
  item_id: string;
  item_name: string;
  invalid_count: number;
  duplicate_count: number;
  total_count: number;
  displayed_count: number;
  ideas: AdminExtractionExcludedIdea[];
}

export interface AdminCuratorDecisionIdea {
  idea_id: string;
  response_id: string;
  participant_id: string;
  original: string;
  normalized: string;
  mapping_status: IdeaStatus;
  decision:
    | "MATCH_EXISTING"
    | "CREATE_NEW"
    | "INVALID"
    | "CURATOR_OBJECT_GUARD"
    | "MISSING_DECISION";
  code_id: string | null;
  code_name: string | null;
  confidence: number;
  reason: string;
  created_at: string;
}

export interface AdminCuratorAudit {
  item_id: string;
  item_name: string;
  match_existing_count: number;
  create_new_count: number;
  invalid_count: number;
  guarded_count: number;
  total_count: number;
  displayed_count: number;
  decisions: AdminCuratorDecisionIdea[];
}

export interface AdminCodebookSummary {
  item_id: string;
  item_name: string;
  calibration_status: string;
  qualifying_response_count: number;
  qualifying_participant_count: number;
  contributing_idea_count: number;
  scoring_min_participants: number;
  scoring_min_responses: number;
  active_version: number | null;
  pending_idea_count: number;
  extraction_invalid_count: number;
  extraction_duplicate_count: number;
  accepted_code_count: number;
  rejected_code_count: number;
  codes: AdminCodebookCode[];
}

export interface AdminCodePatch {
  name?: string;
  description?: string;
  validation_status?: "ACCEPTED" | "UNCERTAIN" | "REJECTED";
  admin_locked?: boolean;
}
