"""
litellm Gateway 통합 클라이언트.

명세 `docs/youtube_monitor_spec.md` 기준:
- 경로 A (Gemini native passthrough):  POST {base_url}/gemini/v1beta/models/{model}:generateContent?key={api_key}
- 경로 B (OpenAI 호환):               POST {base_url}/v1/chat/completions (Authorization: Bearer {api_key})
- 모델 목록:                          GET  {base_url}/v1/models
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

import httpx

from app.services.youtube.json_parse import JsonParseError, gemini_finish_reason, parse_llm_json
from app.services.youtube.settings_manager import AIGatewaySettings, get_youtube_settings_manager


class LiteLLMError(RuntimeError):
    pass


def _normalize_litellm_base_url(raw: str) -> str:
    """
    litellm Base URL을 httpx가 요구하는 절대 URL 형태로 맞춘다.
    `litellm:4000`처럼 스킴이 없으면 `litellm`이 비-http(s) 스킴으로 파싱되어
    "Request URL is missing an 'http://' or 'https://' protocol" 오류가 난다.
    """
    u = (raw or "").strip()
    if not u:
        return ""
    lower = u.lower()
    if lower.startswith("http://") or lower.startswith("https://"):
        return u.rstrip("/")
    return f"http://{u}".rstrip("/")


@dataclass(frozen=True)
class ModelInfo:
    id: str


@dataclass(frozen=True)
class ModelsResponse:
    models: List[ModelInfo]

    @classmethod
    def from_openai_models(cls, payload: Dict[str, Any]) -> "ModelsResponse":
        data = payload.get("data") or []
        models = []
        for m in data:
            mid = m.get("id")
            if mid:
                models.append(ModelInfo(id=mid))
        return cls(models=models)


@dataclass(frozen=True)
class AnalyzerResult:
    """분석 결과(구조화 JSON) + 원본 응답 일부"""

    data: Dict[str, Any]
    raw_text: str


@dataclass(frozen=True)
class ChatResult:
    content: str
    raw: Dict[str, Any]

    @classmethod
    def from_openai_chat_completion(cls, payload: Dict[str, Any]) -> "ChatResult":
        try:
            content = payload["choices"][0]["message"]["content"]
        except Exception as e:
            raise LiteLLMError("chat completions 응답 파싱 실패") from e
        return cls(content=content or "", raw=payload)


def _pick_text_from_gemini(payload: Dict[str, Any]) -> str:
    """
    Gemini generateContent 응답에서 텍스트 파트 추출.
    예상: candidates[0].content.parts[0].text
    """
    try:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        content = (candidates[0].get("content") or {}) if isinstance(candidates[0], dict) else {}
        parts = content.get("parts") or []
        if not parts:
            return ""
        first = parts[0]
        if isinstance(first, dict):
            return first.get("text") or ""
        return ""
    except Exception:
        return ""


class LiteLLMClient:
    def __init__(
        self,
        settings: AIGatewaySettings,
        client: httpx.AsyncClient | None = None,
        models_cache_ttl_sec: float = 60.0,
    ):
        normalized = _normalize_litellm_base_url(settings.base_url)
        if not normalized:
            raise LiteLLMError("AI Gateway base_url이 비어 있습니다.")
        self._settings = settings
        self._base_url = normalized
        self._client = client or httpx.AsyncClient(timeout=300.0)
        self._models_cache_ttl = models_cache_ttl_sec
        self._models_cache: ModelsResponse | None = None
        self._models_cache_exp: float = 0.0

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def api_key(self) -> str:
        return self._settings.api_key

    async def get_models(self, force_refresh: bool = False) -> ModelsResponse:
        now = time.monotonic()
        if not force_refresh and self._models_cache and now < self._models_cache_exp:
            return self._models_cache

        resp = await self._client.get(
            f"{self.base_url}/v1/models",
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
        )
        if resp.status_code != 200:
            raise LiteLLMError(f"/v1/models 실패: {resp.status_code} - {resp.text}")
        models = ModelsResponse.from_openai_models(resp.json())
        self._models_cache = models
        self._models_cache_exp = now + self._models_cache_ttl
        return models

    async def analyze_video_native(
        self,
        model: str,
        video_url: str,
        prompt: str,
        response_schema: Dict[str, Any] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AnalyzerResult:
        """
        경로 A: Gemini native passthrough.
        - model: 'gemini-2.5-flash' 처럼 suffix만 쓰는 경우가 많지만, 사용자가 그대로 넣어도 동작하게 둔다.
        """
        if not self.api_key:
            raise LiteLLMError("AI Gateway api_key가 비어 있습니다.")

        # LiteLLM 형식(예: "gemini/gemini-2.5-flash")에서 모델 ID만 추출
        model_id = model.split("/")[-1] if "/" in model else model
        url = f"{self.base_url}/gemini/v1beta/models/{model_id}:generateContent"
        body: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"fileData": {"fileUri": video_url}}, {"text": prompt}],
                }
            ],
        }
        gen_cfg: Dict[str, Any] = {"responseMimeType": "application/json"}
        if temperature is not None:
            gen_cfg["temperature"] = temperature
        if max_output_tokens is not None:
            gen_cfg["maxOutputTokens"] = max_output_tokens
        if response_schema is not None:
            gen_cfg["responseSchema"] = response_schema
        body["generationConfig"] = gen_cfg

        resp = await self._client.post(url, params={"key": self.api_key}, json=body)
        if resp.status_code != 200:
            raise LiteLLMError(f"Gemini native 분석 실패: {resp.status_code} - {resp.text}")

        payload = resp.json()
        finish = gemini_finish_reason(payload)
        if finish == "MAX_TOKENS":
            raise LiteLLMError(
                "Gemini 출력이 토큰 한도(MAX_TOKENS)에서 잘렸습니다. "
                "설정의 max_tokens를 늘리거나 full_analysis_md 길이를 줄여 주세요."
            )

        raw_text = _pick_text_from_gemini(payload)
        if not raw_text:
            raise LiteLLMError("Gemini 응답에서 텍스트를 찾지 못했습니다.")

        try:
            data = parse_llm_json(raw_text)
        except JsonParseError as e:
            hint = " (출력 잘림 가능)" if finish else ""
            raise LiteLLMError(f"Gemini 구조화 출력 JSON 파싱 실패{hint}: {e}") from e
        return AnalyzerResult(data=data, raw_text=raw_text)

    async def chat(
        self,
        model: str,
        messages: Sequence[Dict[str, Any]],
        response_format: Dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        """
        경로 B: OpenAI 호환 chat completions.
        - response_format은 litellm 구성에 따라 지원 여부가 다를 수 있어 optional.
        """
        if not self.api_key:
            raise LiteLLMError("AI Gateway api_key가 비어 있습니다.")

        body: Dict[str, Any] = {"model": model, "messages": list(messages)}
        if response_format is not None:
            body["response_format"] = response_format
        if temperature is not None:
            body["temperature"] = temperature
        if max_tokens is not None:
            body["max_tokens"] = max_tokens

        resp = await self._client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
        )
        if resp.status_code != 200:
            raise LiteLLMError(f"chat completions 실패: {resp.status_code} - {resp.text}")
        return ChatResult.from_openai_chat_completion(resp.json())


def get_litellm_client(
    settings: AIGatewaySettings | None = None, client: httpx.AsyncClient | None = None
) -> LiteLLMClient:
    cfg = settings or get_youtube_settings_manager().get_ai_gateway()
    return LiteLLMClient(settings=cfg, client=client)
