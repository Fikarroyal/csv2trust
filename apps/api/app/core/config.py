import os
from pathlib import Path

_p = Path(__file__).resolve().parents
ROOT = _p[4] if len(_p) > 4 else Path.cwd()


class Settings:
    """Konfigurasi dari environment variable. Tidak ada API key yang di-hardcode."""

    def __init__(self):
        self.data_dir = Path(os.getenv("DATA_DIR") or ROOT / "data")
        self.database_url = os.getenv("DATABASE_URL") or f"sqlite:///{self.data_dir / 'csv2trust.db'}"
        self.max_upload_mb = int(os.getenv("MAX_UPLOAD_SIZE_MB") or 150)
        self.llm_provider = (os.getenv("LLM_PROVIDER") or "mock").lower()
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.local_llm_url = os.getenv("LOCAL_LLM_URL") or "http://localhost:11434/v1"
        self.cors_origins = (os.getenv("CORS_ORIGINS") or "http://localhost:3000").split(",")
        self.rate_limit_per_min = int(os.getenv("RATE_LIMIT_PER_MIN") or 120)
        for sub in ("uploads", "processed"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


settings = Settings()
