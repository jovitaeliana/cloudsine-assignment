import type { ScanDetail } from "../types";

const STYLES: Record<string, string> = {
  clean: "bg-green-100 border-green-400 text-green-900",
  suspicious: "bg-yellow-100 border-yellow-400 text-yellow-900",
  malicious: "bg-red-100 border-red-400 text-red-900",
};

export function VerdictCard({ scan }: { scan: ScanDetail }) {
  const verdict = scan.verdict ?? "clean";
  const stats = scan.stats ?? {};
  return (
    <div className={`border-2 rounded-lg p-4 ${STYLES[verdict]}`}>
      <div className="flex justify-between items-start">
        <div>
          <p className="text-sm opacity-70">{scan.filename}</p>
          <h2 className="text-2xl font-bold capitalize">{verdict}</h2>
        </div>
        <div className="text-right text-sm">
          <p>Malicious: {stats.malicious ?? 0}</p>
          <p>Suspicious: {stats.suspicious ?? 0}</p>
          <p>Harmless: {stats.harmless ?? 0}</p>
          <p>Undetected: {stats.undetected ?? 0}</p>
        </div>
      </div>
    </div>
  );
}
