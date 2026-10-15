"""Configuration loader that retrieves the LLM model name and settings from .env."""

from __future__ import annotations

import os
from pathlib import Path
from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
LEVEL_DIR = BASE_DIR / "Level"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "learning_app.db"
STATIC_DIR = Path(__file__).resolve().parent / "static"


def reload_env() -> dict[str, str]:
    """Load and return environment variables from the .env file."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)
        raw = dotenv_values(ENV_PATH)
        return {k: v for k, v in raw.items() if v is not None}
    load_dotenv(override=True)
    return {}


def get_model_name() -> str:
    """Retrieve the configured LLM model name from the .env file."""
    env_map = reload_env()
    model = (
        env_map.get("GEMINI_MODEL")
        or env_map.get("MODEL_NAME")
        or env_map.get("LLM_MODEL")
        or os.getenv("GEMINI_MODEL")
        or os.getenv("MODEL_NAME")
        or os.getenv("LLM_MODEL")
    )
    if not model:
        raise ValueError("Model name not found in .env (expected GEMINI_MODEL).")
    return model.strip()


def get_gcp_settings() -> dict[str, str | bool]:
    """Return Google Cloud / Vertex AI configuration from .env."""
    env_map = reload_env()
    project = env_map.get("GOOGLE_CLOUD_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT", "")
    location = env_map.get("GOOGLE_CLOUD_LOCATION") or os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    use_enterprise_raw = (
        env_map.get("GOOGLE_GENAI_USE_ENTERPRISE")
        or env_map.get("GOOGLE_GENAI_USE_VERTEXAI")
        or os.getenv("GOOGLE_GENAI_USE_ENTERPRISE")
        or os.getenv("GOOGLE_GENAI_USE_VERTEXAI")
        or "True"
    )
    use_vertex = str(use_enterprise_raw).strip().lower() in ("true", "1", "yes")
    api_key = env_map.get("GEMINI_API_KEY") or env_map.get("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
    return {
        "project": project,
        "location": location,
        "use_vertex": use_vertex,
        "api_key": api_key,
        "model_name": get_model_name(),
        "env_file": str(ENV_PATH),
    }
