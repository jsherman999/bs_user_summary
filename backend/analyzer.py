from __future__ import annotations

import collections
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any, Callable

from backend.llm_assessor import assess_topic_alignment

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9']+")
URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@[A-Za-z0-9._-]+")

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
    "not",
    "but",
    "all",
    "will",
    "what",
    "who",
    "one",
    "its",
    "it's",
    "im",
    "i'm",
    "dont",
    "don't",
    "cant",
    "can't",
    "just",
    "get",
    "got",
    "also",
    "really",
    "than",
    "then",
    "there",
    "their",
    "about",
    "into",
    "out",
    "now",
    "still",
    "more",
    "some",
    "any",
    "very",
    "new",
    "would",
    "could",
    "should",
    "can",
    "because",
    "where",
    "way",
    "right",
    "like",
}

PLATFORM_NOISE_TOKENS = {
    "app",
    "bsky",
    "bluesky",
    "profile",
    "social",
    "com",
    "http",
    "https",
    "www",
    "did",
    "atproto",
    "xrpc",
    "cid",
    "uri",
    "plc",
}

TOPIC_KEYWORDS = {
    "technology": {"tech", "software", "ai", "code", "coding", "dev", "developer", "programming"},
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

MIN_TAKE_SIGNAL = 5


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
    cleaned = URL_RE.sub(" ", text)
    cleaned = MENTION_RE.sub(" ", cleaned)
    return [token.lower() for token in TOKEN_RE.findall(cleaned)]


def _identity_roots(handle: str, profile: dict[str, Any] | None) -> tuple[set[str], set[str]]:
    blocked_tokens: set[str] = set()
    blocked_prefixes: set[str] = set()

    handle_parts = [part.lower() for part in re.split(r"[^A-Za-z0-9]+", handle) if len(part) > 1]
    for part in handle_parts:
        blocked_tokens.add(part)
        if len(part) >= 4:
            blocked_prefixes.add(part[:4])

    if profile:
        display_name = profile.get("display_name") or profile.get("displayName") or ""
        if isinstance(display_name, str):
            for token in _tokenize(display_name):
                blocked_tokens.add(token)
                if len(token) >= 4:
                    blocked_prefixes.add(token[:4])

    return blocked_tokens, blocked_prefixes


def _pick_top_terms(
    posts: list[dict[str, Any]], handle: str, profile: dict[str, Any] | None = None, top_n: int = 15
) -> list[dict[str, Any]]:
    counts: collections.Counter[str] = collections.Counter()
    blocked = {handle, handle.split(".")[0], *PLATFORM_NOISE_TOKENS}
    identity_tokens, identity_prefixes = _identity_roots(handle, profile)
    blocked.update(identity_tokens)

    for post in posts:
        text = post.get("text") or ""
        for token in _tokenize(text):
            if token in STOPWORDS:
                continue
            if token in blocked:
                continue
            if any(token.startswith(prefix) for prefix in identity_prefixes):
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
        if signal.total < MIN_TAKE_SIGNAL:
            uncertainty_notes.append(
                f"{signal.topic} appears in the sample, but there are fewer than {MIN_TAKE_SIGNAL} mentions, so stance is uncertain."
            )
            continue

        balance = signal.positive - signal.negative
        if signal.positive == 0 and signal.negative == 0:
            stance = "no clear sentiment"
        elif balance >= 2:
            stance = "mostly supportive"
        elif balance <= -2:
            stance = "mostly critical"
        else:
            stance = "mixed"

        confidence = 0.35 + min(signal.total, 12) * 0.03 + min(abs(balance), 6) * 0.04
        if stance in {"mixed", "no clear sentiment"}:
            confidence = min(confidence, 0.7)
        confidence = min(0.9, round(confidence, 2))
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


def _comparison_slice(feed_items: list[dict[str, Any]], start: dt.datetime, end: dt.datetime) -> dict[str, float]:
    window = []
    for item in feed_items:
        ts = _parse_timestamp(item.get("created_at"))
        if ts is None:
            continue
        if start <= ts < end:
            window.append(item)

    total = len(window)
    replies = len([item for item in window if item.get("is_reply")])
    return {
        "items": float(total),
        "replies": float(replies),
        "reply_ratio": round((replies / total) if total else 0.0, 3),
    }


def _build_comparison(feed_items: list[dict[str, Any]], comparison_window_days: int) -> dict[str, Any] | None:
    timestamps = [_parse_timestamp(item.get("created_at")) for item in feed_items]
    timestamps = [ts for ts in timestamps if ts is not None]
    if not timestamps:
        return None

    latest = max(timestamps)
    recent_end = latest + dt.timedelta(seconds=1)
    recent_start = recent_end - dt.timedelta(days=comparison_window_days)
    prior_end = recent_start
    prior_start = prior_end - dt.timedelta(days=comparison_window_days)

    recent = _comparison_slice(feed_items, recent_start, recent_end)
    prior = _comparison_slice(feed_items, prior_start, prior_end)

    delta_items = int(recent["items"] - prior["items"])
    delta_replies = int(recent["replies"] - prior["replies"])
    delta_reply_ratio = round(recent["reply_ratio"] - prior["reply_ratio"], 3)

    direction = "flat"
    if delta_items > 0:
        direction = "higher"
    elif delta_items < 0:
        direction = "lower"

    return {
        "window_days": comparison_window_days,
        "recent_window": {
            "start": recent_start.isoformat(),
            "end": recent_end.isoformat(),
            "items": int(recent["items"]),
            "replies": int(recent["replies"]),
            "reply_ratio": recent["reply_ratio"],
        },
        "prior_window": {
            "start": prior_start.isoformat(),
            "end": prior_end.isoformat(),
            "items": int(prior["items"]),
            "replies": int(prior["replies"]),
            "reply_ratio": prior["reply_ratio"],
        },
        "delta": {
            "items": delta_items,
            "replies": delta_replies,
            "reply_ratio": delta_reply_ratio,
            "activity_direction": direction,
        },
    }


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

    return [claim for claim in claims if claim.get("evidence_ids")]


def summarize_public_history(
    raw_data: dict[str, Any],
    comparison_window_days: int = 30,
    llm_options: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
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

    top_terms = _pick_top_terms(feed_items, handle=handle, profile=profile)
    evidence = _build_evidence(feed_items)
    signals = _collect_topic_signals(evidence)
    top_topics = [{"topic": signal.topic, "count": signal.total} for signal in signals if signal.total >= 2][:5]
    takes, uncertainty_notes = _build_takes(signals)
    llm_assessment = assess_topic_alignment(
        evidence=evidence,
        top_topics=top_topics,
        takes=takes,
        options=llm_options,
        progress_callback=progress_callback,
    )
    claims = _build_claims(metrics=metrics, evidence=evidence, takes=takes, handle=handle)
    comparison = _build_comparison(feed_items, comparison_window_days=max(7, min(90, comparison_window_days)))

    summary_text_parts: list[str] = []
    if metrics["sample_size"] == 0:
        summary_text_parts.append("No public posts or replies were retrieved in this run.")
    else:
        summary_text_parts.append(f"Analyzed {metrics['sample_size']} recent public items from @{handle}.")
        summary_text_parts.extend(claim["text"] for claim in claims)
        if comparison:
            direction = comparison["delta"]["activity_direction"]
            summary_text_parts.append(
                f"Compared with the prior {comparison['window_days']}-day window, activity is {direction}."
            )
        llm_alignments = llm_assessment.get("topic_alignments") or []
        if llm_assessment.get("source") == "llm" and llm_alignments:
            top_alignment = llm_alignments[0]
            summary_text_parts.append(
                f"LLM alignment signal is strongest on {top_alignment['topic']} ({top_alignment['alignment']})."
            )
        if not takes:
            summary_text_parts.append("Topic-specific takes are limited due to weak or sparse signals.")

    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "comparison_window_days": max(7, min(90, comparison_window_days)),
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
        "llm_assessment": llm_assessment,
        "evidence": evidence,
        "comparison": comparison,
        "uncertainty_notes": uncertainty_notes,
        "honesty_notes": [
            "This summary is based only on sampled public BlueSky content fetched during this run.",
            "No private data is accessed.",
            "Claims are included only when linked to concrete evidence items.",
        ],
        "summary_text": " ".join(summary_text_parts),
    }
