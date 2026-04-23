import logging

from google import genai
from google.genai import types
from google.genai.errors import ServerError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

log = logging.getLogger(__name__)


def _top_flagged(vendor_results: dict, limit: int = 5) -> dict:
    flagged = {
        engine: (info.get("result") or "flagged")
        for engine, info in (vendor_results or {}).items()
        if info.get("category") in {"malicious", "suspicious"}
    }
    return dict(list(flagged.items())[:limit])


def build_system_instruction(
    *,
    filename: str,
    verdict: str,
    stats: dict,
    flagged_engines: dict,
) -> str:
    if flagged_engines:
        flagged_lines = "\n".join(f"  - {eng}: {det}" for eng, det in flagged_engines.items())
    else:
        flagged_lines = "  (none)"
    return (
        "You are helping a non-technical user understand a file scan result.\n"
        "Use plain, friendly language. Avoid jargon. Be concise.\n"
        "End each answer with one sentence about what the user should do next.\n\n"
        f"Scan context:\n"
        f"  Filename: {filename}\n"
        f"  Overall verdict: {verdict}\n"
        f"  VirusTotal stats: {stats}\n"
        "  Antivirus engines that flagged the file:\n"
        f"{flagged_lines}"
    )


def _to_gemini_contents(history: list[dict]) -> list[dict]:
    """Map DB message rows to Gemini SDK Content shape.

    DB role 'assistant' becomes Gemini role 'model'.
    """
    out = []
    for m in history:
        role = "model" if m["role"] == "assistant" else "user"
        out.append({"role": role, "parts": [{"text": m["content"]}]})
    return out


class GeminiClient:
    def __init__(self, *, api_key: str, model: str, fallback_model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._fallback_model = fallback_model

    @retry(
        retry=retry_if_exception_type(ServerError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )
    def _generate_with(self, model: str, contents: list[dict], system_instruction: str) -> str:
        response = self._client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        return (response.text or "").strip()

    def chat(self, *, history: list[dict], scan_summary: dict) -> str:
        """Send a multi-turn chat; retries primary, then tries fallback once.

        history: list of {role: 'user'|'assistant', content: str} ordered chronologically.
        scan_summary: dict with filename, verdict, stats, flagged_engines.
        """
        system_instruction = build_system_instruction(
            filename=scan_summary["filename"],
            verdict=scan_summary["verdict"],
            stats=scan_summary.get("stats") or {},
            flagged_engines=scan_summary.get("flagged_engines") or {},
        )
        contents = _to_gemini_contents(history)

        try:
            return self._generate_with(self._model, contents, system_instruction)
        except ServerError:
            log.warning(
                "Primary Gemini model %s exhausted, trying fallback %s",
                self._model,
                self._fallback_model,
            )
            return self._generate_with(self._fallback_model, contents, system_instruction)
