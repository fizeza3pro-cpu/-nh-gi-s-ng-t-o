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
  line_index: number;
  functional_signature: FunctionalSignature;
  curator_decision: string;
}

export interface FunctionalSignature {
  goal: string;
  object_role: string;
  mechanism: string;
  transformation: string;
  target: string;
  context: string;
}

export interface MappingResult {
  ideas: MappedIdea[];
}

export interface PerIdeaScore {
  original: string;
  normalized: string;
  code: string;
  originality: number;
  elaboration: number;
  meaningful_word_count: number;
  elaboration_details: Record<string, string>;
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
  resolution_pending?: boolean;
  scores_stale?: boolean;
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
  processing_state: "QUEUED" | "RUNNING" | "SCORING" | "DONE" | "FAILED";
  status_message: string;
}

export type ParticipantGender =
  | "male"
  | "female"
  | "other"
  | "prefer_not_to_say";

export type AiUsageGroup = "LOW" | "HIGH";

export interface ParticipantProfile {
  full_name: string;
  age: number;
  gender: ParticipantGender;
  occupation: string;
  ai_usage_group: AiUsageGroup;
}

export interface Participant extends ParticipantProfile {
  id: string;
  email_masked: string | null;
  email_verified_at: string | null;
  created_at: string;
}

export interface ParticipantIdentity {
  access_token?: string | null;
  id: string;
  full_name: string | null;
  email_masked: string | null;
  email_verified_at: string | null;
  ai_usage_group: AiUsageGroup | null;
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
  processing_state: string;
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
  qualifying_idea_count: number;
  qualifying_participant_count: number;
  scoring_min_participants: number;
  scoring_min_ideas: number;
  accepted_code_count: number;
  uncertain_code_count: number;
  rejected_code_count: number;
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
  synthetic_calibration_responses: number;
  llm_quota_affected_responses: number;
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
  ai_group_stats: AdminAiGroupStats[];
}

export interface AdminAiGroupStats {
  group: AiUsageGroup;
  participant_count: number;
  response_count: number;
  final_response_count: number;
  mean_fluency: number | null;
  mean_flexibility: number | null;
  mean_originality: number | null;
  mean_elaboration: number | null;
}

export interface AdminParticipantSummary {
  id: string;
  full_name: string | null;
  email_masked: string | null;
  email_verified_at: string | null;
  age: number | null;
  gender: string | null;
  occupation: string | null;
  ai_usage_group: AiUsageGroup | null;
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
  maturity_status: "ACTIVE" | "MERGED";
  confidence: number;
  relevance_reason: string;
  rejection_reason: string;
  created_by: string;
  admin_locked: boolean;
  merged_into_id: string | null;
  merged_into_name: string | null;
  response_count: number;
  participant_count: number;
  idea_count: number;
  contributing_response_count: number;
  contributing_participant_count: number;
  contributing_idea_count: number;
  frequency: number;
  created_at: string;
  functional_key: string;
  functional_signature: FunctionalSignature;
  inclusion_rules: string[];
  exclusion_rules: string[];
  positive_examples: string[];
  embedding_model: string;
  centroid_count: number;
  centroid_revision: number;
  scope_revision: number;
  drift_flag: boolean;
  scope_history: Array<{
    changed_at?: string;
    change?: string;
    reason?: string;
    previous?: { name?: string };
    current?: { name?: string };
    absorbed_code_ids?: string[];
  }>;
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
    | "EXPAND_EXISTING"
    | "OUT_OF_CODEBOOK"
    | "UNCERTAIN"
    | "POLICY_REJECTED"
    | "SCOPE_REJECTED"
    | "INVALID"
    | "CURATOR_OBJECT_GUARD"
    | "MISSING_DECISION";
  code_id: string | null;
  code_name: string | null;
  confidence: number;
  reason: string;
  created_at: string;
  functional_signature: FunctionalSignature;
  mapping_evidence: Record<string, unknown>;
}

export interface AdminCuratorAudit {
  item_id: string;
  item_name: string;
  match_existing_count: number;
  create_new_count: number;
  expand_existing_count: number;
  invalid_count: number;
  guarded_count: number;
  total_count: number;
  displayed_count: number;
  decisions: AdminCuratorDecisionIdea[];
}

export interface AdminCodeOption {
  id: string;
  name: string;
}

export interface AdminMappingReviewIdea {
  idea_id: string;
  response_id: string;
  participant_id: string;
  original: string;
  normalized: string;
  decision: string;
  confidence: number;
  reason: string;
  review_status: "PENDING" | "RESOLVED";
  review_payload: Record<string, unknown>;
  functional_signature: FunctionalSignature;
  mapping_evidence: Record<string, unknown>;
  ai_diagnostics: {
    stages?: Array<{
      stage: string;
      model?: string;
      attempts: number;
      latency_ms: number;
      usage: Record<string, number>;
      reasoning_effort?: string | null;
      failed?: boolean;
    }>;
    usage?: Record<string, number>;
    latency_ms?: number;
  };
  created_at: string;
}

export interface AdminMappingReviewList {
  item_id: string;
  item_name: string;
  pending_count: number;
  total_count: number;
  reviews: AdminMappingReviewIdea[];
  code_options: AdminCodeOption[];
}

export interface AdminMappingReviewResolution {
  action: "CREATE_NEW" | "MATCH_EXISTING" | "MARK_INVALID";
  expected_codebook_epoch: number;
  existing_code_id?: string | null;
  code_name?: string | null;
  code_description?: string | null;
  functional_signature?: FunctionalSignature | null;
  inclusion_rules?: string[] | null;
  exclusion_rules?: string[] | null;
  positive_examples?: string[] | null;
  note: string;
}

export interface AdminMappingReviewResult {
  idea_id: string;
  response_id: string;
  review_status: "RESOLVED";
  resolution: AdminMappingReviewResolution["action"];
  code_id: string | null;
  code_name: string | null;
  scoring_status: string;
}

export interface AdminCodebookOverview {
  item_id: string;
  item_name: string;
  calibration_status: string;
  codebook_epoch: number;
  qualifying_response_count: number;
  qualifying_participant_count: number;
  contributing_idea_count: number;
  scoring_min_participants: number;
  scoring_min_ideas: number;
  pending_idea_count: number;
  extraction_invalid_count: number;
  extraction_duplicate_count: number;
  accepted_code_count: number;
  rejected_code_count: number;
}

export interface AdminCodebookSummary extends AdminCodebookOverview {
  code_page: number;
  code_page_size: number;
  code_total: number;
  code_page_count: number;
  codes: AdminCodebookCode[];
}
