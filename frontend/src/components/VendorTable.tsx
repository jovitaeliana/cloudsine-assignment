import type { ScanDetail } from "../types";

export function VendorTable({ scan }: { scan: ScanDetail }) {
  const results = scan.vendor_results ?? {};
  const rows = Object.entries(results).sort(([a], [b]) => a.localeCompare(b));
  if (rows.length === 0) return null;

  return (
    <div className="mt-6">
      <h3 className="font-semibold mb-2">Per-engine results</h3>
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
            {rows.map(([engine, info]) => (
              <tr key={engine} className="odd:bg-white even:bg-gray-50">
                <td className="p-2 border-b">{engine}</td>
                <td className="p-2 border-b capitalize">{info.category}</td>
                <td className="p-2 border-b">{info.result ?? "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
