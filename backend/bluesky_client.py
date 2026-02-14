from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


BASE_URL = "https://public.api.bsky.app/xrpc"
USER_AGENT = "bs-user-summary/0.1"


class BlueSkyError(RuntimeError):
    """Raised when a BlueSky API call fails."""


@dataclass(slots=True)
class FetchOptions:
    max_items: int = 200
    request_timeout_s: float = 15.0
    max_retries: int = 3


class BlueSkyClient:
    def __init__(self, base_url: str = BASE_URL, user_agent: str = USER_AGENT) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent

    def _request_json(self, path: str, params: dict[str, Any], timeout: float, retries: int) -> dict[str, Any]:
        query = urllib.parse.urlencode(params)
        url = f"{self.base_url}/{path}?{query}"
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

        for attempt in range(1, retries + 1):
            req = urllib.request.Request(url=url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    payload = response.read().decode("utf-8")
                    return json.loads(payload)
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 500, 502, 503, 504} and attempt < retries:
                    time.sleep(0.75 * attempt)
                    continue
                raise BlueSkyError(f"BlueSky HTTP {exc.code}: {body}") from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < retries:
                    time.sleep(0.75 * attempt)
                    continue
                raise BlueSkyError(f"BlueSky request failed: {exc}") from exc

        raise BlueSkyError("BlueSky request failed after retries")

    def resolve_handle(self, handle: str, options: FetchOptions) -> str:
        payload = self._request_json(
            "com.atproto.identity.resolveHandle",
            {"handle": handle},
            timeout=options.request_timeout_s,
            retries=options.max_retries,
        )
        did = payload.get("did")
        if not did:
            raise BlueSkyError("Could not resolve handle to DID")
        return did

    def get_profile(self, actor: str, options: FetchOptions) -> dict[str, Any]:
        payload = self._request_json(
            "app.bsky.actor.getProfile",
            {"actor": actor},
            timeout=options.request_timeout_s,
            retries=options.max_retries,
        )
        return payload

    def get_author_feed_page(self, actor: str, limit: int, cursor: str | None, options: FetchOptions) -> dict[str, Any]:
        params: dict[str, Any] = {"actor": actor, "limit": limit, "filter": "posts_with_replies"}
        if cursor:
            params["cursor"] = cursor
        payload = self._request_json(
            "app.bsky.feed.getAuthorFeed",
            params,
            timeout=options.request_timeout_s,
            retries=options.max_retries,
        )
        return payload

    def fetch_public_history(
        self,
        handle: str,
        options: FetchOptions | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if options is None:
            options = FetchOptions()

        normalized_handle = handle.strip().lstrip("@").lower()
        if progress_callback:
            progress_callback(
                {
                    "stage": "fetch-resolve",
                    "message": f"Resolving handle @{normalized_handle}",
                    "current": 0,
                    "total": max(1, options.max_items),
                    "meta": {"handle": normalized_handle},
                }
            )
        did = self.resolve_handle(normalized_handle, options)
        if progress_callback:
            progress_callback(
                {
                    "stage": "fetch-profile",
                    "message": f"Fetching public profile for @{normalized_handle}",
                    "current": 0,
                    "total": max(1, options.max_items),
                    "meta": {"did": did},
                }
            )
        profile = self.get_profile(did, options)

        feed_items: list[dict[str, Any]] = []
        cursor: str | None = None
        page_size = 100

        while len(feed_items) < options.max_items:
            page = self.get_author_feed_page(did, min(page_size, options.max_items - len(feed_items)), cursor, options)
            cursor = page.get("cursor")
            feed = page.get("feed") or []
            if not feed:
                break

            for item in feed:
                post = item.get("post") or {}
                author = post.get("author") or {}
                if author.get("did") != did:
                    continue

                record = post.get("record") or {}
                text = record.get("text", "")
                if not isinstance(text, str):
                    text = ""

                feed_items.append(
                    {
                        "uri": post.get("uri", ""),
                        "cid": post.get("cid", ""),
                        "indexed_at": post.get("indexedAt", ""),
                        "created_at": record.get("createdAt", ""),
                        "text": text,
                        "langs": record.get("langs", []),
                        "is_reply": bool(record.get("reply")),
                        "reply_root": ((record.get("reply") or {}).get("root") or {}).get("uri"),
                        "reply_parent": ((record.get("reply") or {}).get("parent") or {}).get("uri"),
                        "reply_count": post.get("replyCount", 0),
                        "repost_count": post.get("repostCount", 0),
                        "like_count": post.get("likeCount", 0),
                        "quote_count": post.get("quoteCount", 0),
                    }
                )

                if len(feed_items) >= options.max_items:
                    break

            if progress_callback:
                progress_callback(
                    {
                        "stage": "fetch-feed",
                        "message": f"Fetched {len(feed_items)} public posts/replies",
                        "current": len(feed_items),
                        "total": max(1, options.max_items),
                        "meta": {
                            "fetched_posts": len(feed_items),
                            "requested_posts": max(1, options.max_items),
                            "cursor_present": bool(cursor),
                        },
                    }
                )

            if not cursor:
                break

        if progress_callback:
            progress_callback(
                {
                    "stage": "fetch-complete",
                    "message": f"Fetch complete ({len(feed_items)} items)",
                    "current": len(feed_items),
                    "total": max(1, options.max_items),
                    "meta": {
                        "fetched_posts": len(feed_items),
                        "requested_posts": max(1, options.max_items),
                        "did": did,
                    },
                }
            )

        return {
            "fetched_at": int(time.time()),
            "handle": normalized_handle,
            "did": did,
            "profile": {
                "did": profile.get("did"),
                "handle": profile.get("handle"),
                "display_name": profile.get("displayName"),
                "description": profile.get("description"),
                "followers_count": profile.get("followersCount"),
                "follows_count": profile.get("followsCount"),
                "posts_count": profile.get("postsCount"),
                "indexed_at": profile.get("indexedAt"),
                "labels": profile.get("labels", []),
            },
            "feed_items": feed_items,
        }
