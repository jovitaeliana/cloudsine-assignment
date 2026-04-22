import { useEffect, useState } from "react";

import { uploadFile } from "./api/client";
import { AIExplanation } from "./components/AIExplanation";
import { RecentScans } from "./components/RecentScans";
import { UploadZone } from "./components/UploadZone";
import { VendorTable } from "./components/VendorTable";
import { VerdictCard } from "./components/VerdictCard";
import { useRecentScans } from "./hooks/useRecentScans";
import { useScanPoll } from "./hooks/useScanPoll";

export default function App() {
  const [activeScanId, setActiveScanId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const { scan, error: pollError } = useScanPoll(activeScanId);
  const { scans, refresh } = useRecentScans();

  useEffect(() => {
    if (scan && (scan.status === "complete" || scan.status === "failed")) {
      refresh();
    }
  }, [scan, refresh]);

  async function handleFile(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      const res = await uploadFile(file);
      setActiveScanId(res.scan_id);
      refresh();
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b">
        <div className="max-w-6xl mx-auto px-4 py-4">
          <h1 className="text-xl font-bold">CloudsineAI Scanner</h1>
          <p className="text-sm text-gray-600">
            Upload a file to scan it with VirusTotal and get a plain-English explanation.
          </p>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 grid grid-cols-1 md:grid-cols-[1fr_280px] gap-6">
        <section>
          <UploadZone onFileSelected={handleFile} disabled={uploading} />
          {uploadError && <p className="mt-3 text-red-700">{uploadError}</p>}

          {scan && (
            <div className="mt-6">
              {scan.status === "pending" && (
                <p className="text-gray-600">Scanning... this usually takes 15-60 seconds.</p>
              )}
              {scan.status === "failed" && (
                <p className="text-red-700">
                  Scan failed: {scan.error_message ?? "unknown error"}
                </p>
              )}
              {scan.status === "complete" && (
                <>
                  <VerdictCard scan={scan} />
                  <VendorTable scan={scan} />
                  <AIExplanation scanId={scan.id} initial={scan.ai_explanation} />
                </>
              )}
            </div>
          )}
          {pollError && <p className="mt-3 text-red-700">{pollError}</p>}
        </section>

        <aside className="bg-white border rounded-lg p-4">
          <h2 className="font-semibold mb-3">Recent scans</h2>
          <RecentScans
            scans={scans}
            selectedId={activeScanId}
            onSelect={(id) => setActiveScanId(id)}
          />
        </aside>
      </main>
    </div>
  );
}
