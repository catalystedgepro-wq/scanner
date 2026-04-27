#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_SERVER_URL = "http://localhost:1995"
DEFAULT_TIMEOUT_SECONDS = 2.5
SEARCHABLE_MEMORY_TYPES = {"episodic_memory", "foresight", "event_log"}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _clean_csv(values: str | None, fallback: Sequence[str]) -> tuple[str, ...]:
    if not values:
        return tuple(fallback)
    cleaned = tuple(part.strip() for part in values.split(",") if part.strip())
    return cleaned or tuple(fallback)


@dataclass(frozen=True)
class EverOSConfig:
    enabled: bool
    server_url: str
    user_id: str
    group_id: str
    top_k: int
    memory_types: tuple[str, ...]
    retrieve_method: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


class EverOSRequestError(RuntimeError):
    pass


def load_config(env: Mapping[str, str] | None = None) -> EverOSConfig:
    env = env or os.environ
    return EverOSConfig(
        enabled=_truthy(env.get("EVEROS_ENABLED")),
        server_url=(env.get("EVEROS_BASE_URL") or DEFAULT_SERVER_URL).rstrip("/"),
        user_id=env.get("EVEROS_USER_ID") or "cerebro-operator",
        group_id=env.get("EVEROS_GROUP_ID") or "cerebro-stack",
        top_k=max(1, int(env.get("EVEROS_TOP_K", "5"))),
        memory_types=_clean_csv(env.get("EVEROS_MEMORY_TYPES"), ("episodic_memory", "profile")),
        retrieve_method=(env.get("EVEROS_RETRIEVE_METHOD") or "hybrid").strip() or "hybrid",
        timeout_seconds=max(1.0, float(env.get("EVEROS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))),
    )


def is_enabled(cfg: EverOSConfig | None = None) -> bool:
    return (cfg or load_config()).enabled


def _decode_json(raw: bytes) -> dict:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {"status": "ok"}
    return json.loads(text)


def _request(
    cfg: EverOSConfig,
    method: str,
    path: str,
    params: Mapping[str, object] | None = None,
    payload: Mapping[str, object] | None = None,
) -> dict:
    query = ""
    if params:
        serializable = {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
        if serializable:
            query = f"?{urlencode(serializable, doseq=True)}"
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(f"{cfg.server_url}{path}{query}", data=body, headers=headers, method=method.upper())
    try:
        with urlopen(req, timeout=cfg.timeout_seconds) as resp:
            return _decode_json(resp.read())
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EverOSRequestError(f"EverOS HTTP {exc.code} {path}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise EverOSRequestError(f"EverOS connection failed for {path}: {exc.reason}") from exc


def healthcheck(cfg: EverOSConfig | None = None) -> dict:
    return _request(cfg or load_config(), "GET", "/health")


def backend_available(cfg: EverOSConfig | None = None) -> bool:
    cfg = cfg or load_config()
    if not cfg.enabled:
        return False
    try:
        status = healthcheck(cfg).get("status", "")
    except EverOSRequestError:
        return False
    return str(status).lower() in {"healthy", "ok"}


def message_id(id_seed: str, role: str, content: str) -> str:
    payload = f"{id_seed}:{role}:{content}".encode("utf-8")
    return f"em_{hashlib.sha256(payload).hexdigest()[:24]}"


def _stringify(value: object) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return str(value)


def render_note(
    title: str,
    body: str = "",
    metadata: Mapping[str, object] | None = None,
) -> str:
    lines: list[str] = [title.strip()]
    if body.strip():
        lines.append(body.strip())
    if metadata:
        lines.append("metadata:")
        for key, value in metadata.items():
            lines.append(f"- {key}: {_stringify(value)}")
    return "\n".join(line for line in lines if line).strip()


def save_messages(
    messages: Sequence[Mapping[str, str]],
    *,
    cfg: EverOSConfig | None = None,
    flush: bool = False,
    id_seed: str = "",
    user_id: str | None = None,
    group_id: str | None = None,
    scene: str = "assistant",
    raw_data_type: str = "AgentConversation",
) -> int:
    cfg = cfg or load_config()
    if not cfg.enabled or not messages:
        return 0

    stamp_ms = int(time.time() * 1000)
    user_id = user_id or cfg.user_id
    group_id = group_id or cfg.group_id
    id_seed = id_seed or f"{scene}:{stamp_ms}"
    saved = 0

    for index, message in enumerate(messages):
        role = (message.get("role") or "assistant").strip() or "assistant"
        content = (message.get("content") or "").strip()
        if not content:
            continue
        sender = role if role == "assistant" else user_id
        payload = {
            "message_id": message_id(id_seed, role, content),
            "create_time": time.strftime(
                "%Y-%m-%dT%H:%M:%S",
                time.gmtime((stamp_ms + index) / 1000),
            )
            + "Z",
            "role": role,
            "sender": sender,
            "sender_name": sender,
            "content": content,
            "group_id": group_id,
            "group_name": group_id,
            "scene": scene,
            "raw_data_type": raw_data_type,
        }
        if flush and index == len(messages) - 1:
            payload["flush"] = True
        _request(cfg, "POST", "/api/v1/memories", payload=payload)
        saved += 1

    return saved


def save_note(
    title: str,
    *,
    body: str = "",
    metadata: Mapping[str, object] | None = None,
    cfg: EverOSConfig | None = None,
    flush: bool = True,
    id_seed: str = "",
    user_id: str | None = None,
    group_id: str | None = None,
    scene: str = "assistant",
    raw_data_type: str = "CerebroEvent",
    role: str = "assistant",
) -> int:
    content = render_note(title, body=body, metadata=metadata)
    return save_messages(
        [{"role": role, "content": content}],
        cfg=cfg,
        flush=flush,
        id_seed=id_seed,
        user_id=user_id,
        group_id=group_id,
        scene=scene,
        raw_data_type=raw_data_type,
    )


def search_memories(
    query: str,
    *,
    cfg: EverOSConfig | None = None,
    user_id: str | None = None,
    group_id: str | None = None,
    top_k: int | None = None,
    memory_types: Iterable[str] | None = None,
    retrieve_method: str | None = None,
) -> dict:
    cfg = cfg or load_config()
    memory_types = tuple(memory_types or cfg.memory_types)
    search_types = [item for item in memory_types if item in SEARCHABLE_MEMORY_TYPES]
    want_profile = "profile" in memory_types

    if not search_types and not want_profile:
        return {"status": "ok", "result": {"profiles": [], "memories": [], "pending_messages": []}}

    params = {
        "query": query,
        "user_id": user_id or cfg.user_id,
        "group_id": group_id or cfg.group_id,
        "top_k": top_k or cfg.top_k,
        "retrieve_method": retrieve_method or cfg.retrieve_method,
        "memory_types": search_types or ["episodic_memory"],
    }
    search_result = _request(cfg, "GET", "/api/v1/memories/search", params=params)

    profiles: list[object] = []
    if want_profile:
        profile_result = _request(
            cfg,
            "GET",
            "/api/v1/memories",
            params={
                "user_id": user_id or cfg.user_id,
                "group_id": group_id or cfg.group_id,
                "memory_type": "profile",
                "limit": 1,
            },
        )
        profiles = profile_result.get("result", {}).get("memories", []) or []

    result = search_result.get("result", {}) if isinstance(search_result, dict) else {}
    return {
        "status": "ok",
        "result": {
            "profiles": profiles,
            "memories": result.get("memories", []) or [],
            "pending_messages": result.get("pending_messages", []) or [],
        },
    }

