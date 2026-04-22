from google import genai


def _top_flagged(vendor_results: dict, limit: int = 5) -> dict:
    flagged = {
        engine: (info.get("result") or "flagged")
        for engine, info in (vendor_results or {}).items()
        if info.get("category") in {"malicious", "suspicious"}
    }
    return dict(list(flagged.items())[:limit])


def build_prompt(*, filename: str, verdict: str, stats: dict, flagged_engines: dict) -> str:
    if flagged_engines:
        flagged_lines = "\n".join(f"  - {eng}: {det}" for eng, det in flagged_engines.items())
    else:
        flagged_lines = "  (none)"
    return (
        "You are helping a non-technical user understand a file scan result.\n"
        "Explain the result in 2-3 short paragraphs using plain language. Avoid jargon.\n"
        "End with one sentence telling the user what they should do next.\n\n"
        f"Filename: {filename}\n"
        f"Overall verdict: {verdict}\n"
        f"VirusTotal stats: {stats}\n"
        "Antivirus engines that flagged the file:\n"
        f"{flagged_lines}"
    )


class GeminiClient:
    def __init__(self, *, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def explain(
        self,
        *,
        filename: str,
        verdict: str,
        stats: dict,
        vendor_results: dict,
    ) -> str:
        prompt = build_prompt(
            filename=filename,
            verdict=verdict,
            stats=stats,
            flagged_engines=_top_flagged(vendor_results),
        )
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
        )
        return (response.text or "").strip()
