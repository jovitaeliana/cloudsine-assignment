import { useState } from "react";

import { fetchExplanation } from "../api/client";

interface Props {
  scanId: string;
  initial: string | null;
}

export function AIExplanation({ scanId, initial }: Props) {
  const [text, setText] = useState<string | null>(initial);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleExplain() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetchExplanation(scanId);
      setText(r.explanation);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to get explanation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mt-6 border rounded-lg p-4 bg-indigo-50 border-indigo-200">
      <div className="flex justify-between items-center mb-2">
        <h3 className="font-semibold text-indigo-900">Plain-English explanation</h3>
        {!text && (
          <button
            onClick={handleExplain}
            disabled={loading}
            className="px-3 py-1 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "Asking Gemini..." : "Explain this to me"}
          </button>
        )}
      </div>
      {error && <p className="text-red-700 text-sm">{error}</p>}
      {text && <p className="whitespace-pre-line text-indigo-950">{text}</p>}
    </div>
  );
}
