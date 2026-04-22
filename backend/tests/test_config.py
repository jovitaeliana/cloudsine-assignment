from app.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("VIRUSTOTAL_API_KEY", "vt-test")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host:5432/d")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

    s = Settings(_env_file=None)

    assert s.virustotal_api_key == "vt-test"
    assert s.gemini_api_key == "gm-test"
    assert s.environment == "development"
    assert s.cors_allowed_origins == ["http://localhost:5173"]


def test_settings_parses_multiple_cors_origins(monkeypatch):
    monkeypatch.setenv("VIRUSTOTAL_API_KEY", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setenv("DATABASE_URL", "x")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://a.com,http://b.com")

    s = Settings(_env_file=None)

    assert s.cors_allowed_origins == ["http://a.com", "http://b.com"]
