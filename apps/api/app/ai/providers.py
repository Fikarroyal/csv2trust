"""Lapisan AI modular. LLM hanya memberi interpretasi skema dan rekomendasi (JSON terstruktur).
Transformasi data selalu dijalankan engine deterministik."""
import json
from abc import ABC, abstractmethod

import httpx

from app.core.config import settings
from app.pipelines.engine import OPS
from app.schemas.api import AIResult


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def interpret(self, payload: dict) -> dict: ...


class MockLLMProvider(LLMProvider):
    """Rule-based, tanpa jaringan. Dipakai sebagai default dan fallback."""
    name = "mock"

    def interpret(self, payload: dict) -> dict:
        cols = [{"column": c["name"], "semantic_type": c["semantic"], "confidence": 0.6 if c["semantic"] == "text" else 0.98}
                for c in payload["columns"]]
        recs = []
        for i in payload["issues"]:
            if i.get("fix_key"):
                op, col = i["fix_key"].split(":", 1)
                recs.append({"column": col, "issue": i["type"], "recommendation": op,
                             "reason": i["suggested_fix"], "confidence": i["confidence"]})
        return {"columns": cols, "recommendations": recs}


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, base_url="https://api.openai.com/v1", api_key="", model="gpt-4o-mini"):
        self.base_url, self.api_key, self.model = base_url.rstrip("/"), api_key, model

    def interpret(self, payload: dict) -> dict:
        system = ("Kamu asisten data quality. Balas HANYA JSON dengan kunci 'columns' "
                  "[{column, semantic_type, confidence 0-1}] dan 'recommendations' "
                  "[{column, issue, recommendation, reason, confidence 0-1}]. "
                  f"Nilai 'recommendation' harus salah satu dari {OPS}. Jangan mengubah atau mengembalikan data.")
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = httpx.post(f"{self.base_url}/chat/completions", headers=headers, timeout=30, json={
            "model": self.model, "temperature": 0, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(payload)}]})
        r.raise_for_status()
        return json.loads(r.json()["choices"][0]["message"]["content"])


class LocalLLMProvider(OpenAIProvider):
    """Server lokal yang kompatibel OpenAI (Ollama, LM Studio, vLLM)."""
    name = "local"


def get_provider() -> LLMProvider:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    if settings.llm_provider == "local":
        return LocalLLMProvider(base_url=settings.local_llm_url, model=settings.openai_model)
    return MockLLMProvider()


def run_ai(df, analysis: dict) -> dict:
    """Kirim hanya nama kolom, sampel nilai, dan ringkasan issue (bukan seluruh dataset)."""
    payload = {
        "columns": [{"name": p["name"], "semantic": p["semantic"],
                     "samples": [v for v in df[p["name"]].head(50).tolist() if str(v).strip()][:5]} for p in analysis["profiles"]],
        "issues": [{k: i[k] for k in ("column", "type", "severity", "suggested_fix", "confidence", "fix_key")} for i in analysis["issues"]],
    }
    provider = get_provider()
    try:
        res = AIResult.model_validate(provider.interpret(payload))
        res.recommendations = [r for r in res.recommendations if r.recommendation in OPS]
        return {**res.model_dump(), "provider": provider.name}
    except Exception:
        res = AIResult.model_validate(MockLLMProvider().interpret(payload))
        return {**res.model_dump(), "provider": f"mock (fallback dari {provider.name})"}
