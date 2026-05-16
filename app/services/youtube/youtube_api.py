"""
YouTube Data API v3 래퍼.

- 채널 입력값(URL/@handle/UC id)을 channel_id로 정규화 후 메타/업로드 플레이리스트 조회
- 업로드 플레이리스트에서 기간 내 영상 ID 목록 조회 (페이지네이션)
- videos.list로 영상 상세를 일괄 조회

쿼터(unit) 사용량은 런타임 메모리에서 일자 기준으로만 관리한다(초기 버전).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from app.services.youtube.settings_manager import PollingSettings, get_youtube_settings_manager


class YouTubeAPIError(RuntimeError):
    pass


class YouTubeQuotaExceededError(YouTubeAPIError):
    pass


@dataclass(frozen=True)
class ChannelMeta:
    channel_id: str
    channel_name: str
    upload_playlist_id: str
    channel_handle: str | None = None
    thumbnail_url: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class PlaylistItemMeta:
    video_id: str
    published_at: str | None
    title: str | None


@dataclass(frozen=True)
class VideoMeta:
    video_id: str
    video_url: str
    title: str
    description: str | None
    thumbnail_url: str | None
    published_at: str
    duration: str | None
    view_count: int | None
    like_count: int | None
    channel_id: str | None = None
    channel_title: str | None = None


_UC_ID_RE = re.compile(r"^UC[a-zA-Z0-9_-]{20,}$")
_HANDLE_RE = re.compile(r"^@[\w.-]{3,}$")


def _normalize_input(s: str) -> str:
    return (s or "").strip()


def _extract_from_url(input_str: str) -> Tuple[str, str | None]:
    """
    return (kind, value)
    kind: 'channel_id' | 'handle' | 'username' | 'custom'
    """
    p = urlparse(input_str)
    path = (p.path or "").strip("/")
    if not path:
        raise YouTubeAPIError("채널 URL이 유효하지 않습니다.")

    parts = path.split("/")
    # /channel/UC....
    if len(parts) >= 2 and parts[0] == "channel":
        return "channel_id", parts[1]
    # /@handle
    if parts[0].startswith("@"):
        return "handle", parts[0]
    # /user/legacyName
    if len(parts) >= 2 and parts[0] == "user":
        return "username", parts[1]
    # /c/customName
    if len(parts) >= 2 and parts[0] == "c":
        return "custom", parts[1]

    # 기타: 마지막 세그먼트를 custom로 취급
    return "custom", parts[-1]


class YouTubeAPIClient:
    def __init__(
        self,
        polling: PollingSettings,
        client: httpx.AsyncClient | None = None,
    ):
        if not polling.youtube_api_key:
            raise YouTubeAPIError("YouTube API 키가 없습니다. (polling.youtube_api_key)")
        self._polling = polling
        self._api_key = polling.youtube_api_key
        self._base_url = "https://www.googleapis.com/youtube/v3"
        self._client = client or httpx.AsyncClient(timeout=20.0)

        self._quota_day: date | None = None
        self._quota_used: int = 0

    async def aclose(self) -> None:
        await self._client.aclose()

    def _consume_quota(self, units: int) -> None:
        today = date.today()
        if self._quota_day != today:
            self._quota_day = today
            self._quota_used = 0
        self._quota_used += units
        if self._quota_used > int(self._polling.youtube_daily_quota or 10000):
            raise YouTubeQuotaExceededError(
                f"YouTube API 쿼터 초과: used={self._quota_used}, limit={self._polling.youtube_daily_quota}"
            )

    async def _get(self, path: str, params: Dict[str, Any], quota_units: int) -> Dict[str, Any]:
        self._consume_quota(quota_units)
        url = f"{self._base_url}/{path.lstrip('/')}"
        params = {**params, "key": self._api_key}
        resp = await self._client.get(url, params=params)
        if resp.status_code != 200:
            raise YouTubeAPIError(f"YouTube API 오류: {resp.status_code} - {resp.text}")
        return resp.json()

    async def resolve_channel(self, input_str: str) -> ChannelMeta:
        """
        입력값 정규화 → channel_id 확보 → channels.list로 메타/업로드 플레이리스트 조회
        """
        s = _normalize_input(input_str)
        if not s:
            raise YouTubeAPIError("채널 입력값이 비어 있습니다.")

        # 1) 직접 UC id
        if _UC_ID_RE.match(s):
            channel_id = s
        # 2) handle
        elif _HANDLE_RE.match(s):
            channel_id = await self._resolve_by_handle(s)
        # 3) URL
        elif s.startswith("http://") or s.startswith("https://"):
            kind, value = _extract_from_url(s)
            if kind == "channel_id":
                channel_id = value or ""
            elif kind == "handle":
                channel_id = await self._resolve_by_handle(value or "")
            elif kind == "username":
                channel_id = await self._resolve_by_username(value or "")
            else:
                # /c/customName 은 search.list fallback (quota↑)
                channel_id = await self._resolve_by_search(value or "")
        else:
            # 기타 문자열: handle로 시도 후 실패 시 search fallback
            if s.startswith("@"):
                channel_id = await self._resolve_by_handle(s)
            else:
                channel_id = await self._resolve_by_search(s)

        meta = await self.get_channel_meta(channel_id)
        return meta

    async def _resolve_by_handle(self, handle: str) -> str:
        if not handle.startswith("@"):
            handle = "@" + handle
        data = await self._get(
            "channels",
            params={"part": "id", "forHandle": handle},
            quota_units=1,
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeAPIError(f"handle로 채널을 찾을 수 없습니다: {handle}")
        return items[0]["id"]

    async def _resolve_by_username(self, username: str) -> str:
        data = await self._get(
            "channels",
            params={"part": "id", "forUsername": username},
            quota_units=1,
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeAPIError(f"username으로 채널을 찾을 수 없습니다: {username}")
        return items[0]["id"]

    async def _resolve_by_search(self, q: str) -> str:
        # search.list는 기본 100 unit
        data = await self._get(
            "search",
            params={"part": "snippet", "q": q, "type": "channel", "maxResults": 1},
            quota_units=100,
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeAPIError(f"search로 채널을 찾을 수 없습니다: {q}")
        channel_id = items[0]["snippet"]["channelId"]
        return channel_id

    async def get_channel_meta(self, channel_id: str) -> ChannelMeta:
        data = await self._get(
            "channels",
            params={"part": "snippet,contentDetails", "id": channel_id},
            quota_units=1,
        )
        items = data.get("items") or []
        if not items:
            raise YouTubeAPIError(f"채널 메타를 찾을 수 없습니다: {channel_id}")
        it = items[0]
        snippet = it.get("snippet") or {}
        cdetails = it.get("contentDetails") or {}
        related = (cdetails.get("relatedPlaylists") or {}) if isinstance(cdetails, dict) else {}
        uploads = related.get("uploads")
        if not uploads:
            raise YouTubeAPIError("업로드 플레이리스트 ID를 찾을 수 없습니다.")

        thumbs = snippet.get("thumbnails") or {}
        thumb_url = None
        for k in ("high", "medium", "default"):
            if k in thumbs and thumbs[k].get("url"):
                thumb_url = thumbs[k]["url"]
                break

        return ChannelMeta(
            channel_id=channel_id,
            channel_name=snippet.get("title") or channel_id,
            upload_playlist_id=uploads,
            channel_handle=snippet.get("customUrl"),
            thumbnail_url=thumb_url,
            description=snippet.get("description"),
        )

    async def get_playlist_items_since(
        self, playlist_id: str, published_after: datetime
    ) -> List[PlaylistItemMeta]:
        """업로드 플레이리스트에서 published_after 이후 영상을 페이지네이션으로 전부 조회."""
        if published_after.tzinfo is None:
            published_after = published_after.replace(tzinfo=timezone.utc)

        out: List[PlaylistItemMeta] = []
        page_token: Optional[str] = None
        while True:
            params: Dict[str, Any] = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._get("playlistItems", params=params, quota_units=1)
            batch = data.get("items") or []
            if not batch:
                break

            reached_older = False
            for it in batch:
                c = it.get("contentDetails") or {}
                s = it.get("snippet") or {}
                vid = c.get("videoId")
                if not vid:
                    continue
                pub_str = s.get("publishedAt")
                if pub_str:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                    if pub_dt < published_after:
                        reached_older = True
                        break
                out.append(
                    PlaylistItemMeta(
                        video_id=vid,
                        published_at=pub_str,
                        title=s.get("title"),
                    )
                )

            if reached_older:
                break
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return out

    async def get_video_details(self, video_ids: Iterable[str]) -> List[VideoMeta]:
        ids = list(dict.fromkeys(v for v in video_ids if v))
        if not ids:
            return []

        out: List[VideoMeta] = []
        chunk_size = 50
        for offset in range(0, len(ids), chunk_size):
            chunk = ids[offset : offset + chunk_size]
            data = await self._get(
                "videos",
                params={
                    "part": "snippet,contentDetails,statistics",
                    "id": ",".join(chunk),
                    "maxResults": len(chunk),
                },
                quota_units=1,
            )
            for it in data.get("items") or []:
                vid = it.get("id")
                snippet = it.get("snippet") or {}
                cdetails = it.get("contentDetails") or {}
                stats = it.get("statistics") or {}

                thumbs = snippet.get("thumbnails") or {}
                thumb_url = None
                for k in ("high", "medium", "default"):
                    if k in thumbs and thumbs[k].get("url"):
                        thumb_url = thumbs[k]["url"]
                        break

                def to_int(x: Any) -> int | None:
                    try:
                        return int(x)
                    except Exception:
                        return None

                out.append(
                    VideoMeta(
                        video_id=vid,
                        video_url=f"https://www.youtube.com/watch?v={vid}",
                        title=snippet.get("title") or "",
                        description=snippet.get("description"),
                        thumbnail_url=thumb_url,
                        published_at=snippet.get("publishedAt") or "",
                        duration=cdetails.get("duration"),
                        view_count=to_int(stats.get("viewCount")),
                        like_count=to_int(stats.get("likeCount")),
                        channel_id=snippet.get("channelId"),
                        channel_title=snippet.get("channelTitle"),
                    )
                )
        return out


def get_youtube_api_client(
    polling: PollingSettings | None = None, client: httpx.AsyncClient | None = None
) -> YouTubeAPIClient:
    polling_cfg = polling or get_youtube_settings_manager().get_polling()
    return YouTubeAPIClient(polling=polling_cfg, client=client)
