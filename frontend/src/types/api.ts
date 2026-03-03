// Frontend TypeScript types for REST API request/response payloads

export interface FileUploadResponse {
  files: Array<{
    id: string;
    original_name: string;
    format: string;
    size_bytes: number;
  }>;
  session_id: string;
}

export interface PipelineExecuteRequest {
  session_id: string;
  pipeline_config_id: string;
}

export interface PipelineExecuteResponse {
  session_id: string;
  status: string;
}

export interface ProviderConfig {
  provider_type: string;
  model_id: string;
  inference_profile_id?: string | null;
  endpoint?: string | null;
  api_key?: string | null;
  region?: string | null;
  temperature?: number;
  max_tokens?: number;
  oauth_config?: unknown | null;
}

export interface AgentConfig {
  name: string;
  model: string;
  provider_config: ProviderConfig;
  description: string;
  system_prompt?: string | null;
  faiss_indexes?: number[];
  tools?: string[];
  template?: string | null;
}

export interface OutputConfig {
  template: string;
  formats: string[];
}

export interface PipelineConfig {
  name: string;
  agents: AgentConfig[];
  output: OutputConfig;
  execution_timeout?: number;
}

export interface PipelineListEntry {
  name: string;
  config: PipelineConfig;
}

export interface PipelineListResponse {
  pipelines: PipelineListEntry[];
}

export interface OutputPreview {
  session_id: string;
  template_id: string;
  template_name: string;
  format: string;
  content_html: string;
  metadata: {
    author: string;
    date: string;
    version: string;
    classification: string;
  };
}
