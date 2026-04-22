import { useCallback, useEffect, useState } from "react";

import { fetchRecentScans } from "../api/client";
import type { ScanSummary } from "../types";

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

  return { scans, error, refresh };
}
