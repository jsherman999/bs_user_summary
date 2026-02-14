from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

TOPIC_ALLOWLIST = {
    "technology",
    "politics",
    "media",
    "community",
    "sports",
    "science",
    "economy",
    "culture",
    "other",
}

STANCE_VALUES = {"for", "against", "mixed", "unclear"}

DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-5-mini"


class LLMUnavailableError(RuntimeError):
    """Raised when the configured LLM provider cannot be used."""


@dataclass(slots=True)
class AssessorConfig:
    enabled: bool = True
    provider: str = "auto"
    model: str = ""
    max_posts: int = 500
    chunk_size: int = 40
    max_text_chars: int = 320
    timeout_s: float = 25.0
    temperature: float = 0.1

    @classmethod
    def from_options(cls, options: dict[str, Any] | None = None) -> "AssessorConfig":
        options = options or {}

        enabled = _parse_bool(options.get("enabled"), default=_parse_bool(os.getenv("BS_LLM_ENABLED"), default=True))
        provider = str(options.get("provider") or os.getenv("BS_LLM_PROVIDER", "auto")).strip().lower()
        if provider not in {"auto", "openai", "openrouter", "none"}:
            provider = "auto"

        model = str(options.get("model") or os.getenv("BS_LLM_MODEL", "")).strip()

        max_posts = _clamp_int(options.get("max_posts"), default=int(os.getenv("BS_LLM_MAX_POSTS", "500")), low=25, high=500)
        chunk_size = _clamp_int(
            options.get("chunk_size"), default=int(os.getenv("BS_LLM_CHUNK_SIZE", "40")), low=10, high=80
        )
        max_text_chars = _clamp_int(
            options.get("max_text_chars"), default=int(os.getenv("BS_LLM_MAX_TEXT_CHARS", "320")), low=80, high=500
        )
        timeout_s = float(options.get("timeout_s") or os.getenv("BS_LLM_TIMEOUT_S", "25"))
        timeout_s = max(5.0, min(timeout_s, 60.0))
        temperature = float(options.get("temperature") or os.getenv("BS_LLM_TEMPERATURE", "0.1"))
        temperature = max(0.0, min(temperature, 1.0))

        return cls(
            enabled=enabled,
            provider=provider,
            model=model,
            max_posts=max_posts,
            chunk_size=chunk_size,
            max_text_chars=max_text_chars,
            timeout_s=timeout_s,
            temperature=temperature,
        )


def _parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(low, min(parsed, high))


def _map_stance_to_alignment(stance: str) -> str:
    stance = (stance or "").strip().lower()
    if stance == "mostly supportive":
        return "for"
    if stance == "mostly critical":
        return "against"
    if stance == "mixed":
        return "mixed"
    return "unclear"


def _build_fallback_assessment(
    top_topics: list[dict[str, Any]],
    takes: list[dict[str, Any]],
    reason: str,
    status: str,
    provider: str,
    model: str,
) -> dict[str, Any]:
    take_by_topic = {str(item.get("topic") or ""): item for item in takes}
    alignments: list[dict[str, Any]] = []

    for topic_item in top_topics[:6]:
        topic = str(topic_item.get("topic") or "").strip().lower()
        if not topic:
            continue

        take = take_by_topic.get(topic)
        if take:
            alignment = _map_stance_to_alignment(str(take.get("stance") or ""))
            confidence = min(0.85, round(float(take.get("confidence") or 0.5) * 0.9, 2))
            evidence_ids = list(take.get("evidence_ids") or [])[:6]
        else:
            alignment = "unclear"
            confidence = 0.45
            evidence_ids = []

        alignments.append(
            {
                "topic": topic,
                "alignment": alignment,
                "confidence": confidence,
                "mention_count": int(topic_item.get("count") or 0),
                "evidence_ids": evidence_ids,
                "counts": {
                    "for": int(topic_item.get("count") or 0) if alignment == "for" else 0,
                    "against": int(topic_item.get("count") or 0) if alignment == "against" else 0,
                    "mixed": int(topic_item.get("count") or 0) if alignment == "mixed" else 0,
                    "unclear": int(topic_item.get("count") or 0) if alignment == "unclear" else 0,
                },
            }
        )

    return {
        "enabled": True,
        "source": "deterministic_fallback",
        "provider": provider,
        "model": model,
        "status": status,
        "fallback_reason": reason,
        "topic_alignments": alignments,
        "overall_summary": "Deterministic topic alignment used because LLM assessment was unavailable.",
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        },
    }


def _resolve_provider(config: AssessorConfig) -> tuple[str, str, str, str, dict[str, str]]:
    provider = config.provider

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()

    if provider == "none":
        raise LLMUnavailableError("LLM provider set to none")

    if provider == "auto":
        if openai_key:
            provider = "openai"
        elif openrouter_key:
            provider = "openrouter"
        else:
            raise LLMUnavailableError("No OPENAI_API_KEY or OPENROUTER_API_KEY configured")

    if provider == "openai":
        if not openai_key:
            raise LLMUnavailableError("OPENAI_API_KEY is required for provider=openai")
        model = config.model or DEFAULT_OPENAI_MODEL
        return (
            provider,
            model,
            "https://api.openai.com/v1/chat/completions",
            openai_key,
            {},
        )

    if provider == "openrouter":
        if not openrouter_key:
            raise LLMUnavailableError("OPENROUTER_API_KEY is required for provider=openrouter")
        model = config.model or DEFAULT_OPENROUTER_MODEL
        extra_headers = {
            "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://localhost"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "bs-user-summary"),
        }
        return (
            provider,
            model,
            "https://openrouter.ai/api/v1/chat/completions",
            openrouter_key,
            extra_headers,
        )

    raise LLMUnavailableError(f"Unsupported provider: {provider}")


def _chunk_evidence(evidence: list[dict[str, Any]], config: AssessorConfig) -> list[list[dict[str, Any]]]:
    selected = evidence[: config.max_posts]
    chunks: list[list[dict[str, Any]]] = []

    for idx in range(0, len(selected), config.chunk_size):
        batch = selected[idx : idx + config.chunk_size]
        chunk: list[dict[str, Any]] = []
        for ev in batch:
            text = str(ev.get("text") or "").strip().replace("\n", " ")
            if len(text) > config.max_text_chars:
                text = text[: config.max_text_chars] + "..."
            chunk.append(
                {
                    "id": str(ev.get("id") or ""),
                    "created_at": ev.get("created_at"),
                    "is_reply": bool(ev.get("is_reply")),
                    "text": text,
                }
            )
        if chunk:
            chunks.append(chunk)

    return chunks


def _build_messages(chunk: list[dict[str, Any]]) -> list[dict[str, str]]:
    system_prompt = (
        "You are a careful analyst of public social media posts. "
        "Infer likely alignment conservatively. "
        "Do not invent evidence. "
        "Return strict JSON only."
    )

    user_payload = {
        "task": "Assess likely alignment by topic from this post chunk.",
        "alignment_values": ["for", "against", "mixed", "unclear"],
        "topics": sorted(TOPIC_ALLOWLIST),
        "rules": [
            "Use only provided posts.",
            "If uncertain, increase unclear_count and lower confidence.",
            "evidence_ids must reference only IDs in this chunk.",
            "Counts should reflect this chunk only.",
        ],
        "required_output_schema": {
            "overall_summary": "string",
            "topic_assessments": [
                {
                    "topic": "string",
                    "for_count": "integer",
                    "against_count": "integer",
                    "mixed_count": "integer",
                    "unclear_count": "integer",
                    "confidence": "number_between_0_and_1",
                    "evidence_ids": ["string"],
                    "reasoning": "string",
                }
            ],
        },
        "posts": chunk,
    }

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=True)},
    ]


def _request_chat_json(
    url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    timeout_s: float,
    temperature: float,
    extra_headers: dict[str, str],
) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }

    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)

    request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMUnavailableError(f"LLM HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise LLMUnavailableError(f"LLM request failed: {exc}") from exc


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise LLMUnavailableError("LLM response missing choices")

    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)

    raise LLMUnavailableError("LLM response content was not parseable text")


def _parse_usage(payload: dict[str, Any]) -> dict[str, int]:
    usage = payload.get("usage") or {}

    in_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    out_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total = int(usage.get("total_tokens") or (in_tokens + out_tokens))

    return {
        "input_tokens": in_tokens,
        "output_tokens": out_tokens,
        "total_tokens": total,
    }


def _normalize_chunk_assessments(
    raw_result: dict[str, Any], valid_ids: set[str]
) -> tuple[list[dict[str, Any]], str]:
    assessments: list[dict[str, Any]] = []

    for entry in raw_result.get("topic_assessments") or []:
        topic = str(entry.get("topic") or "").strip().lower()
        if not topic:
            continue
        if topic not in TOPIC_ALLOWLIST:
            topic = "other"

        counts = {
            "for": max(0, int(entry.get("for_count") or 0)),
            "against": max(0, int(entry.get("against_count") or 0)),
            "mixed": max(0, int(entry.get("mixed_count") or 0)),
            "unclear": max(0, int(entry.get("unclear_count") or 0)),
        }

        if sum(counts.values()) <= 0:
            continue

        confidence = float(entry.get("confidence") or 0.5)
        confidence = max(0.0, min(confidence, 1.0))

        evidence_ids: list[str] = []
        for ev_id in entry.get("evidence_ids") or []:
            ev = str(ev_id)
            if ev in valid_ids and ev not in evidence_ids:
                evidence_ids.append(ev)

        assessments.append(
            {
                "topic": topic,
                "counts": counts,
                "confidence": round(confidence, 2),
                "evidence_ids": evidence_ids[:8],
                "reasoning": str(entry.get("reasoning") or "").strip()[:280],
            }
        )

    summary = str(raw_result.get("overall_summary") or "").strip()[:300]
    return assessments, summary


def _pick_alignment(counts: dict[str, int]) -> tuple[str, int]:
    winner = max(STANCE_VALUES, key=lambda key: counts.get(key, 0))
    total = sum(counts.values())

    if total < 4:
        return "unclear", total

    for_count = counts.get("for", 0)
    against_count = counts.get("against", 0)
    mixed_count = counts.get("mixed", 0)

    if winner == "for" and for_count >= against_count + 2:
        return "for", total
    if winner == "against" and against_count >= for_count + 2:
        return "against", total
    if winner == "mixed" or abs(for_count - against_count) <= 1:
        return "mixed", total

    return "unclear", total


def _aggregate_assessments(
    chunk_assessments: list[dict[str, Any]],
    chunk_summaries: list[str],
    usage_totals: dict[str, int],
    provider: str,
    model: str,
) -> dict[str, Any]:
    topic_rollup: dict[str, dict[str, Any]] = {}

    for item in chunk_assessments:
        topic = item["topic"]
        if topic not in topic_rollup:
            topic_rollup[topic] = {
                "counts": {"for": 0, "against": 0, "mixed": 0, "unclear": 0},
                "confidence_samples": [],
                "evidence_ids": [],
                "reasoning": [],
            }

        bucket = topic_rollup[topic]
        for key in ["for", "against", "mixed", "unclear"]:
            bucket["counts"][key] += int(item["counts"].get(key, 0))

        bucket["confidence_samples"].append(float(item["confidence"]))

        for ev_id in item.get("evidence_ids") or []:
            if ev_id not in bucket["evidence_ids"]:
                bucket["evidence_ids"].append(ev_id)

        reason = str(item.get("reasoning") or "").strip()
        if reason and reason not in bucket["reasoning"]:
            bucket["reasoning"].append(reason)

    topic_alignments: list[dict[str, Any]] = []
    for topic, bucket in topic_rollup.items():
        counts = bucket["counts"]
        alignment, mention_count = _pick_alignment(counts)

        confidence_samples = bucket["confidence_samples"]
        avg_conf = sum(confidence_samples) / len(confidence_samples) if confidence_samples else 0.5
        confidence = min(0.9, round(0.35 + min(mention_count, 20) * 0.02 + (avg_conf * 0.2), 2))
        if alignment == "unclear":
            confidence = min(confidence, 0.65)
        if alignment == "mixed":
            confidence = min(confidence, 0.72)

        topic_alignments.append(
            {
                "topic": topic,
                "alignment": alignment,
                "confidence": confidence,
                "mention_count": mention_count,
                "counts": counts,
                "evidence_ids": bucket["evidence_ids"][:10],
                "reasoning": "; ".join(bucket["reasoning"][:2]),
            }
        )

    topic_alignments.sort(key=lambda row: row["mention_count"], reverse=True)

    combined_summary = " ".join([text for text in chunk_summaries if text][:3]).strip()
    if not combined_summary:
        combined_summary = "LLM topic alignment completed with conservative evidence-linked aggregation."

    return {
        "enabled": True,
        "source": "llm",
        "provider": provider,
        "model": model,
        "status": "ok",
        "topic_alignments": topic_alignments[:8],
        "overall_summary": combined_summary,
        "usage": usage_totals,
    }


def assess_topic_alignment(
    evidence: list[dict[str, Any]],
    top_topics: list[dict[str, Any]],
    takes: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = AssessorConfig.from_options(options)

    if not config.enabled:
        return _build_fallback_assessment(
            top_topics=top_topics,
            takes=takes,
            reason="LLM disabled by configuration",
            status="disabled",
            provider=config.provider,
            model=config.model,
        )

    try:
        provider, model, url, api_key, extra_headers = _resolve_provider(config)
    except LLMUnavailableError as exc:
        return _build_fallback_assessment(
            top_topics=top_topics,
            takes=takes,
            reason=str(exc),
            status="fallback",
            provider=config.provider,
            model=config.model,
        )

    chunks = _chunk_evidence(evidence, config)
    if not chunks:
        return _build_fallback_assessment(
            top_topics=top_topics,
            takes=takes,
            reason="No evidence items available for LLM analysis",
            status="fallback",
            provider=provider,
            model=model,
        )

    all_assessments: list[dict[str, Any]] = []
    all_summaries: list[str] = []
    usage_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    try:
        for chunk in chunks:
            messages = _build_messages(chunk)
            payload = _request_chat_json(
                url=url,
                api_key=api_key,
                model=model,
                messages=messages,
                timeout_s=config.timeout_s,
                temperature=config.temperature,
                extra_headers=extra_headers,
            )
            usage = _parse_usage(payload)
            usage_totals["input_tokens"] += usage["input_tokens"]
            usage_totals["output_tokens"] += usage["output_tokens"]
            usage_totals["total_tokens"] += usage["total_tokens"]

            content = _extract_message_content(payload)
            parsed = json.loads(content)
            valid_ids = {str(item.get("id") or "") for item in chunk}
            chunk_assessments, chunk_summary = _normalize_chunk_assessments(parsed, valid_ids)

            all_assessments.extend(chunk_assessments)
            if chunk_summary:
                all_summaries.append(chunk_summary)

        if not all_assessments:
            raise LLMUnavailableError("LLM response did not contain usable topic assessments")

        return _aggregate_assessments(
            chunk_assessments=all_assessments,
            chunk_summaries=all_summaries,
            usage_totals=usage_totals,
            provider=provider,
            model=model,
        )
    except (json.JSONDecodeError, LLMUnavailableError, KeyError, ValueError) as exc:
        return _build_fallback_assessment(
            top_topics=top_topics,
            takes=takes,
            reason=f"LLM unavailable: {exc}",
            status="fallback",
            provider=provider,
            model=model,
        )
