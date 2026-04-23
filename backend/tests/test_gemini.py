from unittest.mock import MagicMock, patch

import pytest
from google.genai.errors import ClientError, ServerError

from app.services.gemini import GeminiClient, build_system_instruction


def _make_response(text: str):
    resp = MagicMock()
    resp.text = text
    return resp


def test_build_system_instruction_includes_scan_context():
    instr = build_system_instruction(
        filename="virus.js",
        verdict="malicious",
        stats={"malicious": 10, "harmless": 50},
        flagged_engines={"EngineA": "Trojan.X"},
    )
    assert "virus.js" in instr
    assert "malicious" in instr.lower()
    assert "EngineA" in instr
    assert "non-technical" in instr.lower()


def test_chat_sends_full_history_and_returns_text():
    mock_response = _make_response("The file is malicious because...")
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.services.gemini.genai.Client", return_value=mock_client):
        c = GeminiClient(
            api_key="k",
            model="gemini-3.1-flash-lite-preview",
            fallback_model="gemini-3-flash-preview",
        )
        out = c.chat(
            history=[
                {"role": "user", "content": "Explain this"},
                {"role": "assistant", "content": "Here is why..."},
                {"role": "user", "content": "What is Magecart?"},
            ],
            scan_summary={
                "filename": "x.js",
                "verdict": "malicious",
                "stats": {"malicious": 5},
                "flagged_engines": {"A": "X"},
            },
        )
    assert out == "The file is malicious because..."
    call = mock_client.models.generate_content.call_args
    assert call.kwargs["model"] == "gemini-3.1-flash-lite-preview"
    contents = call.kwargs["contents"]
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"  # assistant -> model
    assert contents[2]["role"] == "user"


def test_chat_retries_on_server_error_then_succeeds():
    mock_response = _make_response("recovered")
    mock_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.json.return_value = {"error": {"code": 503, "message": "overloaded"}}
    mock_client.models.generate_content.side_effect = [
        ServerError(503, fake_resp),
        ServerError(503, fake_resp),
        mock_response,
    ]

    with patch("app.services.gemini.genai.Client", return_value=mock_client):
        # Patch tenacity's wait to be instant during the test (so suite runs fast).
        with patch("app.services.gemini.wait_exponential", return_value=lambda *a, **k: 0):
            c = GeminiClient(
                api_key="k",
                model="gemini-3.1-flash-lite-preview",
                fallback_model="gemini-3-flash-preview",
            )
            out = c.chat(
                history=[{"role": "user", "content": "hi"}],
                scan_summary={"filename": "x", "verdict": "clean",
                              "stats": {}, "flagged_engines": {}},
            )

    assert out == "recovered"
    assert mock_client.models.generate_content.call_count == 3


def test_chat_falls_back_to_secondary_after_primary_exhausts():
    mock_response = _make_response("from fallback")
    mock_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.json.return_value = {"error": {"code": 503, "message": "overloaded"}}
    # Primary fails 3x, fallback succeeds on 1st try
    mock_client.models.generate_content.side_effect = [
        ServerError(503, fake_resp),
        ServerError(503, fake_resp),
        ServerError(503, fake_resp),
        mock_response,
    ]

    with patch("app.services.gemini.genai.Client", return_value=mock_client):
        with patch("app.services.gemini.wait_exponential", return_value=lambda *a, **k: 0):
            c = GeminiClient(
                api_key="k",
                model="gemini-3.1-flash-lite-preview",
                fallback_model="gemini-3-flash-preview",
            )
            out = c.chat(
                history=[{"role": "user", "content": "hi"}],
                scan_summary={"filename": "x", "verdict": "clean",
                              "stats": {}, "flagged_engines": {}},
            )

    assert out == "from fallback"
    assert mock_client.models.generate_content.call_count == 4
    last_call = mock_client.models.generate_content.call_args_list[-1]
    assert last_call.kwargs["model"] == "gemini-3-flash-preview"


def test_chat_does_not_retry_on_client_error():
    mock_client = MagicMock()
    fake_resp = MagicMock()
    fake_resp.status_code = 400
    fake_resp.json.return_value = {"error": {"code": 400, "message": "bad"}}
    mock_client.models.generate_content.side_effect = ClientError(400, fake_resp)

    with patch("app.services.gemini.genai.Client", return_value=mock_client):
        c = GeminiClient(
            api_key="k",
            model="gemini-3.1-flash-lite-preview",
            fallback_model="gemini-3-flash-preview",
        )
        with pytest.raises(ClientError):
            c.chat(
                history=[{"role": "user", "content": "hi"}],
                scan_summary={"filename": "x", "verdict": "clean",
                              "stats": {}, "flagged_engines": {}},
            )

    assert mock_client.models.generate_content.call_count == 1
