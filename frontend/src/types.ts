export type ScanStatus = "pending" | "complete" | "failed";
export type Verdict = "clean" | "suspicious" | "malicious";

export interface ScanCreateResponse {
  scan_id: string;
  status: ScanStatus;
  cached: boolean;
}

export interface ScanSummary {
  id: string;
  filename: string;
  sha256: string;
  size_bytes: number;
  status: ScanStatus;
  verdict: Verdict | null;
  created_at: string;
}

export interface ScanDetail extends ScanSummary {
  mime_type: string | null;
  stats: {
    malicious?: number;
    suspicious?: number;
    harmless?: number;
    undetected?: number;
    [k: string]: number | undefined;
  } | null;
  vendor_results: Record<string, { category: string; result: string | null }> | null;
  ai_explanation: string | null;
  error_message: string | null;
  updated_at: string;
}

export interface ScanListResponse {
  items: ScanSummary[];
}

export interface ExplanationResponse {
  explanation: string;
}
