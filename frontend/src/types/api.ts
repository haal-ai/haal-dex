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
