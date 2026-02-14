from __future__ import annotations

import collections
import datetime as dt
import re
from dataclasses import dataclass
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

POSITIVE_WORDS = {
    "love",
    "great",
    "good",
    "helpful",
    "excellent",
    "support",
    "supported",
    "supporting",
    "like",
    "liked",
    "awesome",
}

NEGATIVE_WORDS = {
    "bad",
    "hate",
    "awful",
    "terrible",
    "worse",
    "worst",
    "oppose",
    "against",
    "angry",
    "frustrated",
    "problem",
}


@dataclass(slots=True)
class TopicSignal:
    topic: str
    total: int
    positive: int
    negative: int
    evidence_ids: list[str]


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


def _build_evidence(feed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for idx, item in enumerate(feed_items, start=1):
        tokens = set(_tokenize(item.get("text") or ""))
        topics = [topic for topic, keywords in TOPIC_KEYWORDS.items() if tokens.intersection(keywords)]
        evidence.append(
            {
                "id": f"ev{idx}",
                "uri": item.get("uri"),
                "created_at": item.get("created_at"),
                "text": item.get("text", ""),
                "is_reply": bool(item.get("is_reply")),
                "like_count": int(item.get("like_count") or 0),
                "repost_count": int(item.get("repost_count") or 0),
                "reply_count": int(item.get("reply_count") or 0),
                "quote_count": int(item.get("quote_count") or 0),
                "topics": topics,
            }
        )
    return evidence


def _collect_topic_signals(evidence: list[dict[str, Any]]) -> list[TopicSignal]:
    bucket: dict[str, TopicSignal] = {}

    for ev in evidence:
        text = str(ev.get("text") or "")
        tokens = set(_tokenize(text))
        topics = ev.get("topics") or []
        if not topics:
            continue

        has_positive = bool(tokens.intersection(POSITIVE_WORDS))
        has_negative = bool(tokens.intersection(NEGATIVE_WORDS))

        for topic in topics:
            if topic not in bucket:
                bucket[topic] = TopicSignal(topic=topic, total=0, positive=0, negative=0, evidence_ids=[])
            signal = bucket[topic]
            signal.total += 1
            signal.evidence_ids.append(ev["id"])
            if has_positive:
                signal.positive += 1
            if has_negative:
                signal.negative += 1

    return sorted(bucket.values(), key=lambda x: x.total, reverse=True)


def _build_takes(signals: list[TopicSignal]) -> tuple[list[dict[str, Any]], list[str]]:
    takes: list[dict[str, Any]] = []
    uncertainty_notes: list[str] = []

    for signal in signals[:5]:
        if signal.total < 2:
            uncertainty_notes.append(
                f"{signal.topic} appears in the sample, but there are fewer than 2 mentions, so stance is uncertain."
            )
            continue

        if signal.positive >= signal.negative + 2:
            stance = "mostly supportive"
        elif signal.negative >= signal.positive + 2:
            stance = "mostly critical"
        elif signal.positive == 0 and signal.negative == 0:
            stance = "no clear sentiment"
        else:
            stance = "mixed"

        confidence = min(0.95, round(0.35 + (signal.total * 0.08) + abs(signal.positive - signal.negative) * 0.03, 2))
        statement = f"On {signal.topic}, sampled posts are {stance}."

        takes.append(
            {
                "topic": signal.topic,
                "stance": stance,
                "confidence": confidence,
                "signal_count": signal.total,
                "statement": statement,
                "evidence_ids": signal.evidence_ids[:6],
            }
        )

    return takes, uncertainty_notes


def _build_claims(
    metrics: dict[str, Any], evidence: list[dict[str, Any]], takes: list[dict[str, Any]], handle: str
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []

    if evidence:
        claims.append(
            {
                "id": "claim-activity",
                "type": "activity",
                "text": f"Recent sampled activity for @{handle} includes {metrics['sample_size']} public items across {metrics['active_days']} active days.",
                "confidence": 0.95,
                "evidence_ids": [evidence[0]["id"], evidence[min(len(evidence) - 1, 1)]["id"]],
            }
        )

    reply_evidence = [ev["id"] for ev in evidence if ev.get("is_reply")]
    if reply_evidence:
        reply_pct = round(metrics["reply_ratio"] * 100, 1)
        claims.append(
            {
                "id": "claim-replies",
                "type": "interaction",
                "text": f"Replies are {reply_pct}% of sampled activity, indicating notable engagement in conversations.",
                "confidence": 0.9,
                "evidence_ids": reply_evidence[:6],
            }
        )

    for idx, take in enumerate(takes[:3], start=1):
        if not take["evidence_ids"]:
            continue
        claims.append(
            {
                "id": f"claim-take-{idx}",
                "type": "topic_take",
                "text": take["statement"],
                "confidence": take["confidence"],
                "evidence_ids": take["evidence_ids"],
            }
        )

    # Enforce no unsupported claims.
    return [claim for claim in claims if claim.get("evidence_ids")]


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

    top_terms = _pick_top_terms(feed_items, handle=handle)
    evidence = _build_evidence(feed_items)
    signals = _collect_topic_signals(evidence)
    top_topics = [{"topic": signal.topic, "count": signal.total} for signal in signals[:5]]
    takes, uncertainty_notes = _build_takes(signals)
    claims = _build_claims(metrics=metrics, evidence=evidence, takes=takes, handle=handle)

    summary_text_parts: list[str] = []
    if metrics["sample_size"] == 0:
        summary_text_parts.append("No public posts or replies were retrieved in this run.")
    else:
        summary_text_parts.append(f"Analyzed {metrics['sample_size']} recent public items from @{handle}.")
        summary_text_parts.extend(claim["text"] for claim in claims)
        if not takes:
            summary_text_parts.append("Topic-specific takes are limited due to weak or sparse signals.")

    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "user": {
            "handle": handle,
            "did": raw_data.get("did"),
            "profile": profile,
        },
        "metrics": metrics,
        "top_terms": top_terms,
        "top_topics": top_topics,
        "takes": takes,
        "claims": claims,
        "evidence": evidence,
        "uncertainty_notes": uncertainty_notes,
        "honesty_notes": [
            "This summary is based only on sampled public BlueSky content fetched during this run.",
            "No private data is accessed.",
            "Claims are included only when linked to concrete evidence items.",
        ],
        "summary_text": " ".join(summary_text_parts),
    }
