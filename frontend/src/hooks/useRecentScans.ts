import { useCallback, useEffect, useState } from "react";

import { fetchRecentScans } from "../api/client";
import type { ScanSummary } from "../types";

const POLL_INTERVAL_MS = 5000;

export function useRecentScans() {
  const [scans, setScans] = useState<ScanSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetchRecentScans(20);
      setScans(r.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load scans");
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const hasPending = scans.some((s) => s.status === "pending");
    if (!hasPending) return;
    const id = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [scans, refresh]);

  return { scans, error, refresh };
}
