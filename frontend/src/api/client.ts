import type {
  ExplanationResponse,
  ScanCreateResponse,
  ScanDetail,
  ScanListResponse,
} from "../types";

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`${r.status}: ${detail || r.statusText}`);
  }
  return r.json() as Promise<T>;
}

export async function uploadFile(file: File): Promise<ScanCreateResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/scan", { method: "POST", body: fd });
  return handle<ScanCreateResponse>(r);
}

export async function fetchScan(id: string): Promise<ScanDetail> {
  const r = await fetch(`/api/scan/${id}`);
  return handle<ScanDetail>(r);
}

export async function fetchRecentScans(limit = 20): Promise<ScanListResponse> {
  const r = await fetch(`/api/scans?limit=${limit}`);
  return handle<ScanListResponse>(r);
}

export async function fetchExplanation(id: string): Promise<ExplanationResponse> {
  const r = await fetch(`/api/explain/${id}`, { method: "POST" });
  return handle<ExplanationResponse>(r);
}
