// Frontend TypeScript types for domain models

export interface PipelineConfig {
  name: string;
  agents: AgentConfig[];
  output: { template: string; formats: string[] };
  execution_timeout: number;
}

export interface AgentConfig {
  name: string;
  model: string;
  provider_config: {
    provider_type: string;
    model_id: string;
    inference_profile_id?: string;
    endpoint?: string;
    api_key?: string;
    region?: string;
    temperature: number;
    max_tokens: number;
  };
  description: string;
  system_prompt?: string;
  faiss_indexes: number[];
  tools: string[];
  template?: string;
}

export interface Template {
  id: string;
  name: string;
  format: string;
  structure: Record<string, unknown>;
  validation_rules: Array<{
    field: string;
    rule_type: string;
    parameters: Record<string, unknown>;
  }>;
  required_metadata: string[];
  jinja2_template_path: string;
}

export interface Session {
  id: string;
  user_id: string;
  pipeline_config_id: string;
  status: "pending" | "running" | "completed" | "failed";
  created_at: string;
  completed_at: string | null;
  input_files: string[];
  output_documents: string[];
}

export interface SessionMetrics {
  session_id: string;
  agent_metrics: Array<{
    agent_id: string;
    agent_name: string;
    input_tokens: number;
    output_tokens: number;
    llm_call_count: number;
  }>;
}
