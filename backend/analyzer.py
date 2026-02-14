from __future__ import annotations

import collections
import datetime as dt
import re
from typing import Any

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9']+")

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "by",
    "for",
    "from",
    "has",
    "have",
    "he",
    "her",
    "hers",
    "him",
    "his",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "she",
    "that",
    "the",
    "their",
    "them",
    "they",
    "this",
    "to",
    "was",
    "we",
    "were",
    "with",
    "you",
    "your",
}

TOPIC_KEYWORDS = {
    "technology": {"tech", "software", "ai", "code", "coding", "dev", "developer", "programming", "app"},
    "politics": {"policy", "election", "politics", "government", "senate", "congress", "vote", "voting"},
    "sports": {"sports", "game", "team", "match", "season", "playoffs", "score"},
    "media": {"movie", "film", "show", "music", "album", "book", "podcast", "series"},
    "community": {"community", "friends", "people", "support", "thanks", "appreciate"},
}


def _parse_timestamp(value: str | None) -> dt.datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


def _pick_top_terms(posts: list[dict[str, Any]], handle: str, top_n: int = 15) -> list[dict[str, Any]]:
    counts: collections.Counter[str] = collections.Counter()
    blocked = {handle, handle.split(".")[0]}

    for post in posts:
        text = post.get("text") or ""
        for token in _tokenize(text):
            if token in STOPWORDS:
                continue
            if token in blocked:
                continue
            if len(token) <= 2:
                continue
            counts[token] += 1

    return [{"term": term, "count": count} for term, count in counts.most_common(top_n)]


def _pick_topics(posts: list[dict[str, Any]], top_n: int = 5) -> list[dict[str, Any]]:
    counts: collections.Counter[str] = collections.Counter()

    for post in posts:
        tokens = set(_tokenize(post.get("text") or ""))
        for topic, words in TOPIC_KEYWORDS.items():
            if tokens.intersection(words):
                counts[topic] += 1

    return [{"topic": topic, "count": count} for topic, count in counts.most_common(top_n)]


def summarize_public_history(raw_data: dict[str, Any]) -> dict[str, Any]:
    feed_items: list[dict[str, Any]] = raw_data.get("feed_items") or []
    profile = raw_data.get("profile") or {}
    handle = raw_data.get("handle") or ""

    created_timestamps = [_parse_timestamp(item.get("created_at")) for item in feed_items]
    created_timestamps = [ts for ts in created_timestamps if ts is not None]

    replies = [item for item in feed_items if item.get("is_reply")]
    posts = [item for item in feed_items if not item.get("is_reply")]

    days_active: set[str] = set()
    for item in feed_items:
        ts = _parse_timestamp(item.get("created_at"))
        if ts is not None:
            days_active.add(ts.date().isoformat())

    first_post = min(created_timestamps).isoformat() if created_timestamps else None
    last_post = max(created_timestamps).isoformat() if created_timestamps else None

    if created_timestamps:
        span_days = max(1, (max(created_timestamps) - min(created_timestamps)).days + 1)
        avg_posts_per_day = round(len(feed_items) / span_days, 2)
    else:
        avg_posts_per_day = 0.0

    total_reactions = 0
    for item in feed_items:
        total_reactions += int(item.get("like_count") or 0)
        total_reactions += int(item.get("repost_count") or 0)
        total_reactions += int(item.get("quote_count") or 0)
        total_reactions += int(item.get("reply_count") or 0)

    metrics = {
        "sample_size": len(feed_items),
        "total_posts": len(posts),
        "total_replies": len(replies),
        "reply_ratio": round((len(replies) / len(feed_items)) if feed_items else 0.0, 3),
        "active_days": len(days_active),
        "avg_items_per_day": avg_posts_per_day,
        "first_post_at": first_post,
        "last_post_at": last_post,
        "total_visible_reactions": total_reactions,
    }

    summary_text_parts: list[str] = []
    if metrics["sample_size"] == 0:
        summary_text_parts.append("No public posts or replies were retrieved in this run.")
    else:
        summary_text_parts.append(
            f"Analyzed {metrics['sample_size']} recent public items from @{handle}."
        )
        summary_text_parts.append(
            f"Replies make up {round(metrics['reply_ratio'] * 100, 1)}% of the sampled activity."
        )
        if metrics["avg_items_per_day"]:
            summary_text_parts.append(
                f"Observed pace is about {metrics['avg_items_per_day']} items/day across the sampled date span."
            )

    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "user": {
            "handle": handle,
            "did": raw_data.get("did"),
            "profile": profile,
        },
        "metrics": metrics,
        "top_terms": _pick_top_terms(feed_items, handle=handle),
        "top_topics": _pick_topics(feed_items),
        "summary_text": " ".join(summary_text_parts),
    }
