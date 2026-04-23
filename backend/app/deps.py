from functools import lru_cache

from app.config import get_settings
from app.services.gemini import GeminiClient
from app.services.virustotal import VirusTotalClient


@lru_cache
def get_virustotal_client() -> VirusTotalClient:
    s = get_settings()
    return VirusTotalClient(api_key=s.virustotal_api_key, base_url=s.vt_base_url)


@lru_cache
def get_gemini_client() -> GeminiClient:
    s = get_settings()
    return GeminiClient(
        api_key=s.gemini_api_key,
        model=s.gemini_model,
        fallback_model=s.gemini_fallback_model,
    )
