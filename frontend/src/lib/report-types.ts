import type { Item } from "@/lib/types";

export interface ReportIdeaCounts {
  participant_count: number;
  response_count: number;
  total_ideas: number;
  valid_ideas: number;
  invalid_ideas: number;
  duplicate_ideas: number;
  unclassified_ideas: number;
  pending_code_ideas: number;
  used_code_count: number;
}

export interface ReportObjectGroup extends ReportIdeaCounts {
  item_id: string;
  item_name: string;
  group: "LOW" | "HIGH" | "UNKNOWN";
}

export interface ReportObjectCodes {
  item_id: string;
  item_name: string;
  low_code_count: number;
  high_code_count: number;
  shared_code_count: number;
  total_code_count: number;
}

export interface ReportScoreEstimate {
  n: number;
  mean: number | null;
  sd: number | null;
  sem: number | null;
}

export interface ReportScoreDimension {
  dimension: "originality" | "flexibility" | "fluency" | "elaboration";
  low: ReportScoreEstimate;
  high: ReportScoreEstimate;
  difference: number | null;
  p_value: number | null;
  p_value_holm: number | null;
  test_note: string;
}

export interface AdminResearchReport {
  generated_at: string;
  data_source: "PILOT" | "SURVEY";
  item_id: string | null;
  item_ids: string[];
  available_items: Item[];
  sample: {
    submitted_responses: number;
    analyzed_responses: number;
    excluded_responses: number;
    unfinished_responses: number;
    failed_responses: number;
    ungrouped_responses: number;
    final_scored_responses: number;
    stale_score_responses: number;
    other_source_responses: number;
    score_participants_low: number;
    score_participants_high: number;
    registered_participants_low: number;
    registered_participants_high: number;
    submitted_participants_low: number;
    submitted_participants_high: number;
  };
  totals: ReportIdeaCounts;
  object_groups: ReportObjectGroup[];
  object_codes: ReportObjectCodes[];
  dimensions: ReportScoreDimension[];
  summary_vi: string[];
  methodology_vi: string[];
}
