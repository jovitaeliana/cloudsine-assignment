import { useMemo, useState } from "react";

import type { ScanDetail } from "../types";

const CATEGORY_ORDER: Record<string, number> = {
  malicious: 0,
  suspicious: 1,
  harmless: 2,
  undetected: 3,
};

const CATEGORY_BADGE: Record<string, string> = {
  malicious: "bg-red-100 text-red-800",
  suspicious: "bg-yellow-100 text-yellow-800",
  harmless: "bg-green-100 text-green-700",
  undetected: "bg-gray-100 text-gray-600",
};

const FLAGGED_CATEGORIES = new Set(["malicious", "suspicious"]);

export function VendorTable({ scan }: { scan: ScanDetail }) {
  const [onlyFlagged, setOnlyFlagged] = useState(true);
  const [search, setSearch] = useState("");

  const results = scan.vendor_results ?? {};
  const entries = Object.entries(results);
  const totalCount = entries.length;
  const flaggedCount = useMemo(
    () =>
      entries.filter(([, info]) => FLAGGED_CATEGORIES.has(info.category)).length,
    [entries],
  );

  const filtered = useMemo(() => {
    const needle = search.toLowerCase();
    return entries
      .filter(([engine, info]) => {
        if (onlyFlagged && !FLAGGED_CATEGORIES.has(info.category)) return false;
        if (needle && !engine.toLowerCase().includes(needle)) return false;
        return true;
      })
      .sort(([aEng, aInfo], [bEng, bInfo]) => {
        const aOrder = CATEGORY_ORDER[aInfo.category] ?? 99;
        const bOrder = CATEGORY_ORDER[bInfo.category] ?? 99;
        return aOrder !== bOrder ? aOrder - bOrder : aEng.localeCompare(bEng);
      });
  }, [entries, onlyFlagged, search]);

  if (entries.length === 0) return null;

  return (
    <div className="mt-6">
      <div className="flex justify-between items-center mb-2 flex-wrap gap-2">
        <h3 className="font-semibold">
          Per-engine results ({flaggedCount} of {totalCount} engines flagged)
        </h3>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={onlyFlagged}
              onChange={(e) => setOnlyFlagged(e.target.checked)}
            />
            Show only flagged
          </label>
          <input
            type="text"
            placeholder="Filter engines..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="px-2 py-1 text-sm border rounded"
          />
        </div>
      </div>

      {filtered.length === 0 && onlyFlagged ? (
        <p className="text-sm text-gray-600 italic p-4 bg-gray-50 rounded">
          No engines flagged this file. Uncheck "Show only flagged" to see all{" "}
          {totalCount} engines.
        </p>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-gray-600 italic p-4 bg-gray-50 rounded">
          No engines match "{search}".
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm border">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left p-2 border-b">Engine</th>
                <th className="text-left p-2 border-b">Category</th>
                <th className="text-left p-2 border-b">Detection</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(([engine, info]) => (
                <tr key={engine} className="odd:bg-white even:bg-gray-50">
                  <td className="p-2 border-b">{engine}</td>
                  <td className="p-2 border-b">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        CATEGORY_BADGE[info.category] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {info.category}
                    </span>
                  </td>
                  <td className="p-2 border-b">{info.result ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
