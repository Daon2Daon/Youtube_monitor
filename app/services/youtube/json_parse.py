"""
LLM 구조화 출력(JSON) 파싱 유틸.

모델이 마크다운 코드펜스로 감싸거나, 출력 토큰 한도로 JSON이 중간에 잘리는 경우를 완화한다.
"""

from __future__ import annotations

import json
from typing import Any, Dict


class JsonParseError(ValueError):
    pass


def strip_code_fence(text: str) -> str:
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    lines = [ln for ln in s.splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip()


def extract_json_object(text: str) -> str:
    """첫 '{'부터 마지막 '}'까지 추출."""
    s = (text or "").strip()
    start = s.find("{")
    if start < 0:
        return s
    end = s.rfind("}")
    if end > start:
        return s[start : end + 1]
    return s[start:]


def repair_truncated_json(s: str) -> str:
    """
    토큰 한도 등으로 잘린 JSON을 best-effort로 닫는다.
    - 미종료 문자열에 닫는 따옴표 추가
    - 미닫힌 { [ 스택을 역순으로 닫기
    """
    text = (s or "").rstrip()
    if not text:
        return text

    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
    if in_string:
        text += '"'

    stack: list[str] = []
    in_str = False
    esc = False
    for ch in text:
        if esc:
            esc = False
            continue
        if ch == "\\" and in_str:
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch in "}]" and stack and ch == stack[-1]:
            stack.pop()

    while stack:
        text += stack.pop()
    return text


def _loads_candidates(raw: str) -> Dict[str, Any]:
    base = strip_code_fence(raw)
    variants: list[str] = []
    for candidate in (base, extract_json_object(base)):
        if candidate and candidate not in variants:
            variants.append(candidate)
        repaired = repair_truncated_json(candidate)
        if repaired and repaired not in variants:
            variants.append(repaired)

    last_err: Exception | None = None
    for text in variants:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            last_err = e
            continue
    raise JsonParseError(str(last_err) if last_err else "유효한 JSON 객체를 찾지 못했습니다.")


def parse_llm_json(raw: str) -> Dict[str, Any]:
    """LLM 텍스트 응답에서 분석용 JSON 객체를 파싱."""
    if not (raw or "").strip():
        raise JsonParseError("빈 응답")
    return _loads_candidates(raw)


def gemini_finish_reason(payload: Dict[str, Any]) -> str | None:
    try:
        candidates = payload.get("candidates") or []
        if not candidates:
            return None
        return (candidates[0] or {}).get("finishReason")
    except Exception:
        return None
