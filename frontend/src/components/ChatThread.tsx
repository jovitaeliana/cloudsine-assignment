import { useEffect, useRef, useState } from "react";

import { fetchChatHistory, sendChatMessage } from "../api/client";
import type { ChatMessage, Verdict } from "../types";
import { MessageBubble } from "./MessageBubble";

const CHIPS_BY_VERDICT: Record<string, string[]> = {
  malicious: [
    "What's the worst this file could do?",
    "How do I safely remove it?",
    "How might I have gotten this?",
    "Should I scan my other files?",
  ],
  suspicious: [
    "Why is this borderline?",
    "Should I treat it as malicious?",
    "What would make it definitely unsafe?",
    "How can I verify this elsewhere?",
  ],
  clean: [
    "Is 'clean' 100% safe?",
    "What could change this result later?",
    "What does this file actually do?",
    "How reliable is this verdict?",
  ],
};

const PRESET_OPENER = "Please explain this scan result to me in plain English.";

interface Props {
  scanId: string;
  verdict: Verdict | null;
}

export function ChatThread({ scanId, verdict }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<{ message: string; retriable: boolean } | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoadingHistory(true);
    setMessages([]);
    setError(null);
    fetchChatHistory(scanId)
      .then((r) => {
        if (!cancelled) setMessages(r.messages);
      })
      .catch((e) => {
        if (!cancelled) {
          setError({
            message: e instanceof Error ? e.message : "Failed to load chat",
            retriable: true,
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [scanId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setInput("");
    setSending(true);
    setError(null);

    const tempId = `temp-${Date.now()}`;
    const optimistic: ChatMessage = {
      id: tempId,
      scan_id: scanId,
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, optimistic]);

    try {
      const resp = await sendChatMessage(scanId, trimmed);
      setMessages((m) => {
        const withoutTemp = m.filter((msg) => msg.id !== tempId);
        return [...withoutTemp, resp.user_message, resp.assistant_message];
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong";
      const is503 = msg.includes("503");
      setError({
        message: is503
          ? "Gemini is busy right now. Try again in a moment."
          : msg,
        retriable: true,
      });
    } finally {
      setSending(false);
    }
  }

  function retryLast() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    setMessages((m) => m.filter((msg) => msg.id !== lastUser.id));
    send(lastUser.content);
  }

  const chips = verdict ? CHIPS_BY_VERDICT[verdict] ?? CHIPS_BY_VERDICT.clean : [];
  const isEmpty = !loadingHistory && messages.length === 0;

  return (
    <div className="mt-6 border rounded-lg p-4 bg-indigo-50 border-indigo-200">
      <h3 className="font-semibold text-indigo-900 mb-3">
        Plain-English explanation & chat
      </h3>

      {loadingHistory && (
        <p className="text-sm text-indigo-700">Loading chat...</p>
      )}

      {isEmpty && (
        <div className="text-center py-6">
          <p className="mb-3 text-indigo-800">
            Want a plain-English explanation of this scan?
          </p>
          <button
            onClick={() => send(PRESET_OPENER)}
            disabled={sending}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            {sending ? "Asking Gemini..." : "Explain this scan to me"}
          </button>
        </div>
      )}

      {messages.length > 0 && (
        <div className="max-h-96 overflow-y-auto space-y-3 mb-3 pr-2">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-white border border-indigo-200 px-3 py-2 rounded-lg text-indigo-400 text-sm">
                <span className="inline-block animate-pulse">Thinking...</span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}

      {error && (
        <div className="mb-3 p-2 bg-amber-50 border border-amber-200 rounded text-amber-900 text-sm flex justify-between items-center gap-2">
          <span>⚠️ {error.message}</span>
          {error.retriable && messages.length > 0 && (
            <button
              onClick={retryLast}
              disabled={sending}
              className="px-2 py-1 text-xs bg-amber-600 text-white rounded hover:bg-amber-700 disabled:opacity-50 whitespace-nowrap"
            >
              Retry
            </button>
          )}
        </div>
      )}

      {!isEmpty && chips.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {chips.map((chip) => (
            <button
              key={chip}
              onClick={() => send(chip)}
              disabled={sending}
              className="px-3 py-1 text-xs bg-white border border-indigo-300 rounded-full hover:bg-indigo-100 disabled:opacity-50"
            >
              {chip}
            </button>
          ))}
        </div>
      )}

      {!isEmpty && (
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask a follow-up..."
            disabled={sending}
            className="flex-1 px-3 py-2 border rounded text-sm disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={sending || !input.trim()}
            className="px-4 py-2 bg-indigo-600 text-white rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
