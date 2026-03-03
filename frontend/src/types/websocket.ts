// Frontend TypeScript types for WebSocket events
// These map from Strands graph.stream_async() event types to frontend-friendly events
//
// Strands event mapping:
// multiagent_node_start  → agent_start
// multiagent_node_stream → llm_token
// multiagent_node_stop   → agent_complete (or agent_fail if error)
// multiagent_result      → pipeline_complete

export interface ExecutionEvent {
  type:
    | "agent_start"
    | "agent_complete"
    | "agent_fail"
    | "llm_token"
    | "log_entry"
    | "metrics_update"
    | "pipeline_complete";
  session_id: string;
  timestamp: string;
  data:
    | AgentStatusData
    | LLMStreamToken
    | LogEntryData
    | MetricsData
    | PipelineCompleteData;
}

export interface ChatResponse {
  type: "token" | "complete" | "error";
  session_id: string;
  content: string;
}

export interface AgentStatusData {
  agent_id: string;
  agent_name: string;
  step_number: number;
  status: "pending" | "running" | "completed" | "failed";
  error?: string;
}

export interface LLMStreamToken {
  type: "token" | "complete";
  agent_id: string;
  content: string;
}

export interface LogEntryData {
  agent_id: string;
  level: string;
  message: string;
}

export interface MetricsData {
  agent_id: string;
  input_tokens: number;
  output_tokens: number;
  llm_call_count: number;
}

export interface PipelineCompleteData {
  status: "COMPLETED" | "FAILED";
  execution_order: string[];
  execution_time_ms: number;
  total_tokens: { input: number; output: number };
}
