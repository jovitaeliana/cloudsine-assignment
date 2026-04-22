from unittest.mock import MagicMock, patch

from app.services.gemini import GeminiClient, build_prompt


def test_build_prompt_includes_verdict_and_top_engines():
    prompt = build_prompt(
        filename="virus.js",
        verdict="malicious",
        stats={"malicious": 10, "suspicious": 2, "harmless": 50, "undetected": 5},
        flagged_engines={"EngineA": "Trojan.X", "EngineB": "Downloader.Y"},
    )
    assert "virus.js" in prompt
    assert "malicious" in prompt.lower()
    assert "EngineA" in prompt
    assert "Trojan.X" in prompt
    assert "non-technical" in prompt.lower()


def test_build_prompt_handles_no_flagged_engines():
    prompt = build_prompt(
        filename="safe.js",
        verdict="clean",
        stats={"malicious": 0, "suspicious": 0, "harmless": 70, "undetected": 5},
        flagged_engines={},
    )
    assert "(none)" in prompt


def test_gemini_client_calls_sdk_and_returns_text():
    mock_response = MagicMock()
    mock_response.text = "This file looks suspicious because..."

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.gemini.genai.Client", return_value=mock_client):
        c = GeminiClient(api_key="k", model="gemini-2.5-flash")
        out = c.explain(
            filename="x.js",
            verdict="clean",
            stats={"malicious": 0, "harmless": 70, "suspicious": 0, "undetected": 5},
            vendor_results={},
        )

    assert out == "This file looks suspicious because..."
    mock_client.models.generate_content.assert_called_once()
    call = mock_client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemini-2.5-flash"


def test_gemini_client_filters_flagged_engines_only():
    captured_prompt = {}

    mock_response = MagicMock()
    mock_response.text = "answer"

    mock_client = MagicMock()

    def capture(**kwargs):
        captured_prompt["contents"] = kwargs["contents"]
        return mock_response

    mock_client.models.generate_content.side_effect = capture

    with patch("app.services.gemini.genai.Client", return_value=mock_client):
        c = GeminiClient(api_key="k", model="gemini-2.5-flash")
        c.explain(
            filename="x.js",
            verdict="malicious",
            stats={"malicious": 2},
            vendor_results={
                "EvilEye": {"category": "malicious", "result": "Bad.Thing"},
                "GoodGuy": {"category": "harmless", "result": None},
                "Maybe": {"category": "suspicious", "result": "Susp.Thing"},
            },
        )

    prompt = captured_prompt["contents"]
    assert "EvilEye" in prompt
    assert "Maybe" in prompt
    assert "GoodGuy" not in prompt  # harmless must not be included
