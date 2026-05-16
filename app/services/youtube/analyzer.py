"""
YouTube 영상 분석 파이프라인.
SQLite 변환: pg_insert → sqlite_insert.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy import text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.youtube_video import YoutubeVideo
from app.models.youtube_video_analysis import YoutubeVideoAnalysis
from app.services.youtube.json_parse import JsonParseError, parse_llm_json
from app.services.youtube.llm_client import LiteLLMClient, LiteLLMError
from app.services.youtube.settings_manager import AIGatewaySettings, get_youtube_settings_manager
from app.services.youtube.tag_extractor import extract_and_save_tags

# ---------- 기본 분석 프롬프트 (경쟁사 광고·프로모션) ----------

DEFAULT_ANALYSIS_PROMPT: str = """다음 영상(경쟁사 광고, 프로모션, 신상품 발표 등)을 한국어로 분석해줘.

## 현재 날짜
오늘은 {today}임. 업로드 일시가 {published_at_kst}인 이 영상은 현재 시점에서 이미 게시된 영상이므로 반드시 실제 내용을 기반으로 분석할 것.

## 영상 정보
- 브랜드/채널명: {channel_name}
- 업로드 일시: {published_at_kst}

## 작성 원칙 (반드시 준수)
영상이 '무엇을 보여주는가'(행위/시각 서술)가 아닌, '어떤 타겟에게 무엇을 소구하는가'(핵심 메시지 및 소비자 혜택)를 중심으로 작성.
아래 형태의 메타 서술 표현은 절대 사용 금지:
  금지 표현: ~을 홍보했다 / ~을 소개했다 / ~을 보여주었다 / ~을 강조했다 / ~을 설명했다 / ~을 어필했다

[나쁜 예] "새로운 멤버십 혜택을 소개했다"
[좋은 예] "2030 1인 가구 타겟 월 5천원 구독형 멤버십 출시 — 주요 OTT 결합 할인으로 실용성 소구"

[나쁜 예] "전국망 커버리지의 우수성을 강조했다"
[좋은 예] "도서산간 통신 음영지역 제로(0) 달성 — '어디서든 끊김없는' 카피로 국가대표 통신망 브랜드 신뢰도 구축"

[나쁜 예] "팝업스토어 오픈과 이벤트를 알렸다"
[좋은 예] "오프라인 체험형 팝업스토어 오픈 (일 평균 방문자 300명 수준 타겟) — 플래그십 단말기 대여 및 한정판 굿즈로 Z세대 바이럴 유도"

## 분석 요청 항목
- 한 줄 요약: 캠페인의 핵심 타겟과 소구점(USP)을 한 문장으로 직접 서술.
- 헤드라인: 이모지 1~2개와 캠페인 핵심 키워드를 포함해 40자 이내로 작성.
- 짧은 요약: 타겟 고객, 주요 혜택, 크리에이티브 전략(모델, 카피)을 중심으로 800자 이내 텔레그램용 요약문 작성.
- 핵심 마케팅 포인트 (Bullet points): 캠페인의 주요 혜택·전략·메시지를 5~10개로 정리. 각 항목은 사실과 소구점을 직접 서술 (필요시 수치, 가격, 할인율 괄호 표기). 각 항목 80자 이내.
- 전체 분석: 마크다운 형식으로 '캠페인 개요 / 핵심 소구점(USP) 및 타겟 분석 / 크리에이티브 및 매체 전략' 섹션 포함. **2500자 이내**로 간결히 작성.
- 타임스탬프 포인트: 광고의 핵심 씬, 메인 카피 등장, 제품 시연 장면 등을 hh:mm:ss 형식으로 정리.
- 자사 적용 인사이트: 해당 경쟁사 활동이 자사 브랜드에 미칠 영향이나 대응 전략 아이디어를 3~5개로 정리.
- 등장 인물/기업/상품: 영상에 등장하는 광고 모델, 콜라보 브랜드, 핵심 상품명 추출.
- 브랜드 톤앤매너: 영상의 전체적인 분위기를 trendy/trustworthy/premium/humorous 중 하나로 판단.
- 태그: 캠페인을 대표하는 태그를 5~10개 추출. (예: '5G요금제', 'Z세대', '팝업스토어').
- 신뢰도: 분석의 완성도를 0.0~1.0으로 자기 평가.

## 출력 형식
반드시 아래 JSON 형식으로만 출력. 모든 텍스트는 한국어, '~함', '~임' 형태의 개조식으로 작성.

{{
  "one_line": "string",
  "headline": "string",
  "short_summary_md": "string",
  "bullet_points": ["string"],
  "full_analysis_md": "string",
  "key_points": [{{"timestamp":"hh:mm:ss","point":"string"}}],
  "insights": ["string"],
  "entities": [{{"type":"model|brand|product|keyword","name":"string"}}],
  "brand_tone": "trendy|trustworthy|premium|humorous",
  "tags": [{{"name":"string","type":"target|benefit|concept","weight":0.0}}],
  "confidence_score": 0.0
}}"""

# 하위 호환 (import 경로 유지)
ANALYSIS_PROMPT_V1 = DEFAULT_ANALYSIS_PROMPT
FALLBACK_PROMPT_V1 = DEFAULT_ANALYSIS_PROMPT

REQUIRED_FIELDS = {
    "one_line",
    "headline",
    "short_summary_md",
    "bullet_points",
    "full_analysis_md",
    "brand_tone",
    "confidence_score",
}

BRAND_TONE_VALUES = frozenset({"trendy", "trustworthy", "premium", "humorous"})

PROMPT_VERSION = "v4.1-marketing"

# 마케팅 분석 JSON은 필드가 많아 출력 토큰을 넉넉히 확보
ANALYSIS_MIN_OUTPUT_TOKENS = 16384


@dataclass
class AnalysisPipelineResult:
    data: Dict[str, Any]
    route: str
    model_name: str
    gateway_url: str
    prompt_version: str = PROMPT_VERSION
    raw_text: str = ""
    token_input: Optional[int] = None
    token_output: Optional[int] = None
    cost_usd: Optional[float] = None


class AnalysisFailedError(RuntimeError):
    pass


class AnalysisValidationError(ValueError):
    pass


def _validate(data: Dict[str, Any]) -> None:
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise AnalysisValidationError(f"필수 필드 누락: {missing}")
    tone = data.get("brand_tone") or data.get("sentiment")
    if tone not in BRAND_TONE_VALUES:
        raise AnalysisValidationError(f"brand_tone 값이 잘못됨: {tone!r}")
    score = data.get("confidence_score")
    if not isinstance(score, (int, float)) or not (0.0 <= float(score) <= 1.0):
        raise AnalysisValidationError(f"confidence_score 범위 오류: {score!r}")


def _published_at_kst(published_at_str: str) -> str:
    try:
        dt = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
        from zoneinfo import ZoneInfo
        dt_kst = dt.astimezone(ZoneInfo("Asia/Seoul"))
        return dt_kst.strftime("%Y-%m-%d %H:%M KST")
    except Exception:
        return published_at_str


class AnalysisPipeline:
    def __init__(
        self,
        llm_client: LiteLLMClient,
        ai_settings: AIGatewaySettings,
        notify_callback: Optional[Callable[[int], Any]] = None,
    ):
        self._llm = llm_client
        self._ai = ai_settings
        self._notify_callback = notify_callback

    async def run(
        self,
        video_pk: int,
        video_url: str,
        channel_name: str,
        published_at_str: str,
        custom_prompt: Optional[str] = None,
    ) -> AnalysisPipelineResult:
        from zoneinfo import ZoneInfo

        pub_kst = _published_at_kst(published_at_str)
        today_kst = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y년 %m월 %d일")

        mgr = get_youtube_settings_manager()
        prompt_cfg = mgr.get_prompts()

        template = custom_prompt or prompt_cfg.analysis_prompt or DEFAULT_ANALYSIS_PROMPT
        prompt_text = template.format(
            channel_name=channel_name,
            published_at_kst=pub_kst,
            video_url=video_url,
            today=today_kst,
        )
        output_tokens = max(int(self._ai.max_tokens or 0), ANALYSIS_MIN_OUTPUT_TOKENS)

        # Primary: Gemini native (영상 직접 분석)
        try:
            result = await self._llm.analyze_video_native(
                model=self._ai.primary_model,
                video_url=video_url,
                prompt=prompt_text,
                temperature=self._ai.temperature,
                max_output_tokens=output_tokens,
            )
            _validate(result.data)
            return AnalysisPipelineResult(
                data=result.data,
                route="A",
                model_name=self._ai.primary_model,
                gateway_url=self._ai.base_url,
                raw_text=result.raw_text,
            )
        except (LiteLLMError, AnalysisValidationError) as e:
            print(f"⚠️  Primary 분석 실패 (video_pk={video_pk}): {e}")

        # Fallback: OpenAI 호환 (동일 프롬프트)
        try:
            chat_result = await self._llm.chat(
                model=self._ai.fallback_model,
                messages=[{"role": "user", "content": prompt_text}],
                response_format={"type": "json_object"},
                temperature=self._ai.temperature,
                max_tokens=output_tokens,
            )
            raw_text = chat_result.content.strip()
            try:
                data = parse_llm_json(raw_text)
            except JsonParseError as parse_err:
                raise LiteLLMError(f"Fallback 응답 JSON 파싱 실패: {parse_err}") from parse_err
            _validate(data)
            return AnalysisPipelineResult(
                data=data,
                route="B",
                model_name=self._ai.fallback_model,
                gateway_url=self._ai.base_url,
                raw_text=raw_text,
            )
        except Exception as e:
            raise AnalysisFailedError(f"Primary·Fallback 모두 실패 (video_pk={video_pk}): {e}") from e

    async def save_to_db(
        self,
        session: AsyncSession,
        video_pk: int,
        result: AnalysisPipelineResult,
    ) -> None:
        """SQLite 트랜잭션: video_analysis / tags / video_tags / videos.status."""
        data = result.data
        brand_tone = data.get("brand_tone") or data.get("sentiment")

        analysis_stmt = sqlite_insert(YoutubeVideoAnalysis).values(
            video_pk=video_pk,
            one_line=data.get("one_line", ""),
            headline=data.get("headline"),
            short_summary_md=data.get("short_summary_md", ""),
            bullet_points=data.get("bullet_points"),
            full_analysis_md=data.get("full_analysis_md"),
            full_transcript=None,
            key_points=data.get("key_points"),
            insights=data.get("insights"),
            entities=data.get("entities"),
            sentiment=brand_tone,
            confidence_score=float(data.get("confidence_score") or 0.0),
            model_name=result.model_name,
            gateway_url=result.gateway_url,
            prompt_version=result.prompt_version,
            token_input=result.token_input,
            token_output=result.token_output,
            cost_usd=result.cost_usd,
            analyzed_at=datetime.now(timezone.utc),
        )
        analysis_upsert = analysis_stmt.on_conflict_do_update(
            index_elements=["video_pk"],
            set_={
                "one_line": analysis_stmt.excluded.one_line,
                "headline": analysis_stmt.excluded.headline,
                "short_summary_md": analysis_stmt.excluded.short_summary_md,
                "bullet_points": analysis_stmt.excluded.bullet_points,
                "full_analysis_md": analysis_stmt.excluded.full_analysis_md,
                "key_points": analysis_stmt.excluded.key_points,
                "insights": analysis_stmt.excluded.insights,
                "entities": analysis_stmt.excluded.entities,
                "sentiment": analysis_stmt.excluded.sentiment,
                "confidence_score": analysis_stmt.excluded.confidence_score,
                "model_name": analysis_stmt.excluded.model_name,
                "gateway_url": analysis_stmt.excluded.gateway_url,
                "prompt_version": analysis_stmt.excluded.prompt_version,
                "token_input": analysis_stmt.excluded.token_input,
                "token_output": analysis_stmt.excluded.token_output,
                "cost_usd": analysis_stmt.excluded.cost_usd,
                "analyzed_at": analysis_stmt.excluded.analyzed_at,
            },
        )
        await session.execute(analysis_upsert)

        raw_tags: List[Dict[str, Any]] = data.get("tags") or []
        await extract_and_save_tags(
            session=session,
            video_pk=video_pk,
            raw_tags=raw_tags,
            llm_client=self._llm,
            tagging_model=self._ai.tagging_model,
        )

        await session.execute(
            update(YoutubeVideo)
            .where(YoutubeVideo.video_pk == video_pk)
            .values(analysis_status="done")
        )

        # Telegram 발송은 트랜잭션 커밋 후 호출해야 함 (save_to_db는 보통 begin() 안에서 실행됨).
        # notify_video_callback은 monitor_service / youtube 라우터에서 커밋 뒤 호출.

    async def run_and_save(
        self,
        session: AsyncSession,
        video_pk: int,
        video_url: str,
        channel_name: str,
        published_at_str: str,
        custom_prompt: Optional[str] = None,
    ) -> AnalysisPipelineResult:
        result = await self.run(
            video_pk=video_pk,
            video_url=video_url,
            channel_name=channel_name,
            published_at_str=published_at_str,
            custom_prompt=custom_prompt,
        )
        await self.save_to_db(session, video_pk, result)
        return result


def build_analysis_pipeline(
    llm_client: LiteLLMClient | None = None,
    ai_settings: AIGatewaySettings | None = None,
    notify_callback: Optional[Callable[[int], Any]] = None,
) -> AnalysisPipeline:
    mgr = get_youtube_settings_manager()
    ai = ai_settings or mgr.get_ai_gateway()
    if llm_client is None:
        from app.services.youtube.llm_client import get_litellm_client
        llm_client = get_litellm_client(settings=ai)
    return AnalysisPipeline(llm_client=llm_client, ai_settings=ai, notify_callback=notify_callback)
