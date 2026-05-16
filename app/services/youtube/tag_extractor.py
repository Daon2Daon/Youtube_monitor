"""
YouTube 모니터: 태그 추출·정규화·저장.
SQLite 호환: youtube.tags/youtube.video_tags 대신 tags/video_tags 사용,
ANY(:tag_pks) 대신 IN 절 사용.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.youtube_tag import YoutubeTag
from app.models.youtube_video_tag import YoutubeVideoTag

_ALIAS_MAP: Dict[str, str] = {
    "미 연준": "연준",
    "us fed": "연준",
    "federal reserve": "연준",
    "tsm": "tsmc",
    "s&p": "s&p500",
    "s&p 500": "s&p500",
    "나스닥 100": "나스닥",
    "nasdaq 100": "나스닥",
}

_VALID_TAG_TYPES = {"topic", "ticker", "person", "sector"}


def _normalize_tag_name(name: str) -> str:
    normalized = re.sub(r"\s+", " ", (name or "").strip()).lower()
    return _ALIAS_MAP.get(normalized, normalized)


def _normalize_tag_type(t: str | None) -> str:
    return t if t in _VALID_TAG_TYPES else "topic"


async def _fetch_existing_tags(
    session: AsyncSession, names: Sequence[str]
) -> Dict[str, int]:
    if not names:
        return {}
    stmt = select(YoutubeTag).where(YoutubeTag.name.in_(names))
    result = await session.execute(stmt)
    return {row.name: row.tag_pk for row in result.scalars().all()}


async def _upsert_tags(
    session: AsyncSession, tags: Sequence[Dict[str, Any]]
) -> Dict[str, int]:
    """tags 테이블에 upsert(ON CONFLICT DO NOTHING) 후 {name: tag_pk} 반환."""
    name_to_pk: Dict[str, int] = {}
    for t in tags:
        raw_name = t.get("name") or ""
        name = _normalize_tag_name(raw_name)
        if not name:
            continue
        tag_type = _normalize_tag_type(t.get("type"))

        await session.execute(
            text(
                """
                INSERT INTO tags (name, tag_type)
                VALUES (:name, :tag_type)
                ON CONFLICT (name) DO NOTHING
                """
            ),
            {"name": name, "tag_type": tag_type},
        )

    await session.flush()

    all_names = [
        _normalize_tag_name(t.get("name") or "") for t in tags if t.get("name")
    ]
    if all_names:
        name_to_pk = await _fetch_existing_tags(session, all_names)
    return name_to_pk


async def _upsert_video_tags(
    session: AsyncSession,
    video_pk: int,
    name_to_pk: Dict[str, int],
    tags: Sequence[Dict[str, Any]],
) -> None:
    for t in tags:
        name = _normalize_tag_name(t.get("name") or "")
        tag_pk = name_to_pk.get(name)
        if not tag_pk:
            continue
        weight = float(t.get("weight") or 1.0)
        await session.execute(
            text(
                """
                INSERT INTO video_tags (video_pk, tag_pk, weight)
                VALUES (:video_pk, :tag_pk, :weight)
                ON CONFLICT (video_pk, tag_pk) DO UPDATE SET weight = excluded.weight
                """
            ),
            {"video_pk": video_pk, "tag_pk": tag_pk, "weight": weight},
        )

    # video_count 재계산: SQLite는 ANY() 미지원 → IN (...) 사용
    updated_tag_pks = [pk for pk in name_to_pk.values() if pk]
    if updated_tag_pks:
        # SQLite bindparam with IN은 개별 파라미터로 처리
        placeholders = ", ".join(f":pk_{i}" for i in range(len(updated_tag_pks)))
        params = {f"pk_{i}": pk for i, pk in enumerate(updated_tag_pks)}
        await session.execute(
            text(
                f"""
                UPDATE tags
                SET video_count = (
                    SELECT COUNT(*) FROM video_tags vt WHERE vt.tag_pk = tags.tag_pk
                )
                WHERE tags.tag_pk IN ({placeholders})
                """
            ),
            params,
        )


async def _merge_synonyms_with_llm(
    tags: List[Dict[str, Any]],
    llm_client: Any,
    tagging_model: str,
) -> List[Dict[str, Any]]:
    names_str = ", ".join(t.get("name", "") for t in tags)
    prompt = (
        "아래 태그 목록에서 동의어·유사어를 한국어 표준형으로 통합해주세요.\n"
        "반드시 JSON 배열만 반환: "
        '[{"name":"태그명","type":"topic|ticker|person|sector","weight":0.0~1.0}]\n'
        f"태그 목록: {names_str}"
    )
    try:
        result = await llm_client.chat(
            model=tagging_model,
            messages=[{"role": "user", "content": prompt}],
        )
        merged = json.loads(result.content)
        if isinstance(merged, list) and merged:
            return merged
    except Exception as e:
        print(f"⚠️  태그 동의어 통합 LLM 실패 (원본 사용): {e}")
    return tags


async def extract_and_save_tags(
    session: AsyncSession,
    video_pk: int,
    raw_tags: List[Dict[str, Any]],
    llm_client: Optional[Any] = None,
    tagging_model: Optional[str] = None,
    llm_merge_threshold: int = 5,
) -> int:
    if not raw_tags:
        return 0

    tags = list(raw_tags)

    if llm_client and tagging_model and len(tags) >= llm_merge_threshold:
        tags = await _merge_synonyms_with_llm(tags, llm_client, tagging_model)

    name_to_pk = await _upsert_tags(session, tags)
    await _upsert_video_tags(session, video_pk, name_to_pk, tags)
    return len(name_to_pk)
