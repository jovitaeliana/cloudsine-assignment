import type {
  ChatHistoryResponse,
  ChatResponse,
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

export async function fetchChatHistory(scanId: string): Promise<ChatHistoryResponse> {
  const r = await fetch(`/api/chat/${scanId}`);
  return handle<ChatHistoryResponse>(r);
}

export async function sendChatMessage(
  scanId: string,
  message: string,
): Promise<ChatResponse> {
  const r = await fetch(`/api/chat/${scanId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return handle<ChatResponse>(r);
}
