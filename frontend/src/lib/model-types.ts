export type ThinkingMode = "auto" | "enabled" | "disabled" | "unsupported";

export interface ManagedModel {
  slot: number;
  label: string;
  model_id: string | null;
  quota_key: string | null;
  enabled: boolean;
  context_window: number;
  thinking_mode: ThinkingMode;
  status: string;
  quota_limit: number;
  remaining_tokens: number | null;
  used_tokens: number | null;
  reserved_tokens: number;
  available_tokens: number | null;
  unknown_requests: number;
  balance_confirmed_at: string | null;
  last_request_at: string | null;
}

export interface ModelPoolSnapshot {
  enabled: boolean;
  auto_switch: boolean;
  threshold: number;
  revision: number;
  active_slot: number | null;
  blocked_reason: string;
  provider: string;
  api_key_configured: boolean;
  models: ManagedModel[];
  events: Array<{ id: string; event: string; actor_id: string | null; created_at: string; payload: Record<string, unknown> }>;
  requests: Array<{ id: string; slot: number; model_id: string; stage: string; response_id: string | null;
    status: string; input_tokens: number | null; output_tokens: number | null; total_tokens: number | null;
    reserved_tokens: number; created_at: string; error_code: string }>;
}

export interface ModelConfiguration {
  label: string;
  model_id: string;
  quota_key: string;
  enabled: boolean;
  context_window: number;
  thinking_mode: ThinkingMode;
}
