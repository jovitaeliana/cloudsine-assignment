import { useEffect, useState } from "react";

import { fetchScan } from "../api/client";
import type { ScanDetail } from "../types";

const POLL_INTERVAL_MS = 3000;
const TIMEOUT_MS = 180_000;

export function useScanPoll(scanId: string | null) {
  const [scan, setScan] = useState<ScanDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!scanId) {
      setScan(null);
      setError(null);
      return;
    }
    let cancelled = false;
    const start = Date.now();

    async function tick() {
      if (cancelled) return;
      try {
        const result = await fetchScan(scanId!);
        if (cancelled) return;
        setScan(result);
        if (result.status === "complete" || result.status === "failed") return;
        if (Date.now() - start > TIMEOUT_MS) {
          setError("Scan timed out");
          return;
        }
        setTimeout(tick, POLL_INTERVAL_MS);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Poll failed");
      }
    }

    tick();
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  return { scan, error };
}
