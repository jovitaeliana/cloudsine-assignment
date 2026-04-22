"""Shared pytest fixtures and test-time env defaults.

Sets safe placeholder env vars before `app.*` modules are imported, so unit
tests never need a real .env to be present on the machine.
"""
import os

os.environ.setdefault("VIRUSTOTAL_API_KEY", "test-vt-key")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://cloudsine:change_me_in_prod@localhost:5432/cloudsine_test",
)
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
