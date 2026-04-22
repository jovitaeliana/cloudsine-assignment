import type { ScanSummary } from "../types";

interface Props {
  scans: ScanSummary[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}

const CHIP: Record<string, string> = {
  clean: "bg-green-100 text-green-800",
  suspicious: "bg-yellow-100 text-yellow-800",
  malicious: "bg-red-100 text-red-800",
};

export function RecentScans({ scans, selectedId, onSelect }: Props) {
  if (scans.length === 0) {
    return <p className="text-sm text-gray-500">No scans yet.</p>;
  }
  return (
    <ul className="space-y-1">
      {scans.map((s) => (
        <li key={s.id}>
          <button
            onClick={() => onSelect(s.id)}
            className={`w-full text-left px-3 py-2 rounded hover:bg-gray-100 ${
              selectedId === s.id ? "bg-gray-100" : ""
            }`}
          >
            <p className="font-medium truncate">{s.filename}</p>
            <div className="flex justify-between text-xs mt-1">
              <span
                className={`px-2 py-0.5 rounded ${
                  s.verdict ? CHIP[s.verdict] : "bg-gray-100 text-gray-600"
                }`}
              >
                {s.verdict ?? s.status}
              </span>
              <span className="text-gray-500">
                {new Date(s.created_at).toLocaleString()}
              </span>
            </div>
          </button>
        </li>
      ))}
    </ul>
  );
}
