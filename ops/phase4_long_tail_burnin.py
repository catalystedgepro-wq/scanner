#!/usr/bin/env python3
"""Run a throttled Ollama-backed burn-in against the current unknown universe.

This serves two purposes at once:
1. exercise the local fallback model under real classification load
2. persist accepted long-tail sector classifications into a cache that
   build_universe_gravity.py can read on future recovery passes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
ENTITY_MASTER_PATH = ROOT / "entity_master.json"
DEFAULT_OUTPUT_PATH = ROOT / "memory" / "phase4_cleanup_results.json"
DEFAULT_STATUS_PATH = ROOT / "memory" / "phase4_cleanup_status.json"
DEFAULT_CACHE_PATH = ROOT / ".long_tail_sector_cache.json"
DEFAULT_COMPANY_INFO_CACHE = ROOT / ".phase4_company_info_cache.json"
DEFAULT_MODEL = (
    os.environ.get("LONG_TAIL_BURNIN_MODEL")
    or os.environ.get("OLLAMA_MODEL_SMART")
    or os.environ.get("OLLAMA_MODEL_FAST")
    or "gemma4:latest"
)
DEFAULT_OLLAMA_BASE_URL = (os.environ.get("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1").rstrip("/")
DEFAULT_OLLAMA_API_KEY = os.environ.get("OLLAMA_API_KEY") or "ollama-local"
DEFAULT_USER_AGENT = os.environ.get("SEC_USER_AGENT", "CatalystEdge/1.0 contact@catalystedge.com")
ALLOWED_SECTORS = (
    "tech",
    "semis",
    "biotech",
    "financials",
    "energy",
    "materials",
    "industrials",
    "consumer",
    "staples",
    "comms",
    "utilities",
    "real_estate",
    "unknown",
)
GENERIC_BUCKETS = (
    "closed_end_fund",
    "income_fund",
    "investment_vehicle",
    "business_development_company",
    "holding_company",
    "royalty_trust",
    "adr_foreign_common",
    "otc_derivative_generic",
    "long_tail_unclassified",
    "none",
)
GENERIC_BUCKET_TO_SECTOR = {
    "closed_end_fund": "financials",
    "income_fund": "financials",
    "investment_vehicle": "financials",
    "business_development_company": "financials",
    "royalty_trust": "energy",
}
METADATA_ONLY_BUCKETS = {
    "holding_company",
    "adr_foreign_common",
    "otc_derivative_generic",
    "long_tail_unclassified",
}
SECTOR_NORMALIZATION = {
    "technology": "tech",
    "information technology": "tech",
    "software": "tech",
    "software - infrastructure": "tech",
    "software - application": "tech",
    "information technology services": "tech",
    "semiconductor": "semis",
    "semiconductors": "semis",
    "healthcare": "biotech",
    "health care": "biotech",
    "pharmaceuticals": "biotech",
    "biotechnology": "biotech",
    "financial services": "financials",
    "shell companies": "financials",
    "blank check": "financials",
    "consumer discretionary": "consumer",
    "consumer staples": "staples",
    "communication services": "comms",
    "telecom": "comms",
    "real estate": "real_estate",
    "utilities": "utilities",
}


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_sector(rec: dict) -> str:
    gics = rec.get("gics") or {}
    return str(gics.get("s") or rec.get("sector") or "").strip().lower() or "unknown"


def _system_snapshot() -> dict[str, float | int | None]:
    load1, load5, load15 = os.getloadavg()
    mem_total_kb = 0
    mem_available_kb = 0
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_available_kb = int(line.split()[1])
    except Exception:
        pass
    mem_used_pct = None
    if mem_total_kb and mem_available_kb:
        mem_used_pct = round((1.0 - (mem_available_kb / mem_total_kb)) * 100.0, 2)
    return {
        "load1": round(load1, 3),
        "load5": round(load5, 3),
        "load15": round(load15, 3),
        "mem_used_pct": mem_used_pct,
        "mem_available_mb": round(mem_available_kb / 1024.0, 1) if mem_available_kb else None,
    }


def _wait_for_budget(max_load1: float, max_mem_used_pct: float, cooldown_seconds: float) -> None:
    if max_load1 <= 0 and max_mem_used_pct <= 0:
        return
    while True:
        snapshot = _system_snapshot()
        if max_load1 > 0 and float(snapshot.get("load1") or 0.0) > max_load1:
            time.sleep(max(cooldown_seconds, 2.0))
            continue
        mem_used_pct = snapshot.get("mem_used_pct")
        if max_mem_used_pct > 0 and isinstance(mem_used_pct, (int, float)) and float(mem_used_pct) > max_mem_used_pct:
            time.sleep(max(cooldown_seconds, 2.0))
            continue
        return


def _fetch_sec_company_info(cik: str, company_cache: dict[str, dict]) -> dict[str, Any]:
    padded = str(cik or "").strip().zfill(10)
    if not padded or not padded.strip("0"):
        return {}
    cached = company_cache.get(padded)
    if isinstance(cached, dict):
        return cached
    url = f"https://data.sec.gov/submissions/CIK{padded}.json"
    req = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except Exception:
        company_cache[padded] = {}
        return {}
    info = {
        "name": str(payload.get("name") or "").strip(),
        "sic": payload.get("sic"),
        "sic_description": str(payload.get("sicDescription") or "").strip(),
    }
    company_cache[padded] = info
    return info


def _extract_json_block(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    for candidate in (text, fenced):
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
    match = re.search(r"\{.*\}", fenced or text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_generic_bucket(raw: Any) -> str:
    bucket = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "closed_end": "closed_end_fund",
        "closed_end_trust": "closed_end_fund",
        "fund_vehicle": "investment_vehicle",
        "bdc": "business_development_company",
        "adr": "adr_foreign_common",
        "otc_derivative": "otc_derivative_generic",
        "unclassified": "long_tail_unclassified",
    }
    bucket = aliases.get(bucket, bucket)
    return bucket if bucket in GENERIC_BUCKETS else "none"


def _normalize_sector(raw: Any, generic_bucket: str) -> str:
    sector = str(raw or "").strip().lower().replace("-", "_")
    sector = SECTOR_NORMALIZATION.get(sector, sector)
    if sector in ALLOWED_SECTORS:
        return sector
    mapped = GENERIC_BUCKET_TO_SECTOR.get(generic_bucket)
    if mapped:
        return mapped
    return "unknown"


def _heuristic_bucket(symbol: str, name: str) -> str:
    name_upper = str(name or "").upper()
    symbol_upper = str(symbol or "").upper()
    if "BUSINESS DEVELOPMENT" in name_upper or re.search(r"\bBDC\b", name_upper):
        return "business_development_company"
    if any(token in name_upper for token in ("FUND", "TRUST", "INCOME OPPORTUNITIES", "TOTAL RETURN", "MUNICIPAL", "PREFERRED & INCOME")):
        return "closed_end_fund"
    if "ROYALTY" in name_upper:
        return "royalty_trust"
    if "ADR" in name_upper or symbol_upper.endswith("Y") or symbol_upper.endswith("F"):
        return "adr_foreign_common"
    if re.search(r"[-./](WSA|WSB|WS|WT|W|U|R|RT|UN|PR[A-Z]{1,2}|P[A-Z]{1,2})$", symbol_upper):
        return "otc_derivative_generic"
    return "none"


def _build_prompt(symbol: str, rec: dict, sec_info: dict[str, Any]) -> tuple[str, str]:
    name = str(rec.get("name") or sec_info.get("name") or symbol).strip()
    system = (
        "Classify a market symbol into one canonical sector or generic wrapper bucket. "
        "Return compact JSON only."
    )
    user = (
        f"symbol={symbol}\n"
        f"name={name}\n"
        f"sic={sec_info.get('sic') or ''}\n"
        f"sic_desc={sec_info.get('sic_description') or ''}\n"
        "sector choices: tech, semis, biotech, financials, energy, materials, industrials, consumer, staples, comms, utilities, real_estate, unknown\n"
        "generic_bucket choices: closed_end_fund, income_fund, investment_vehicle, business_development_company, holding_company, royalty_trust, adr_foreign_common, otc_derivative_generic, long_tail_unclassified, none\n"
        'reply exactly as JSON: {"sector":"","confidence":0.0,"generic_bucket":""}'
    )
    return system, user


def _call_ollama(base_url: str, api_key: str, model: str, system: str, user: str, timeout_seconds: float) -> str:
    native_base = base_url.rstrip("/")
    if native_base.endswith("/v1"):
        native_base = native_base[:-3]
    url = f"{native_base}/api/generate"
    payload = {
        "model": model,
        "prompt": f"{system}\n\n{user}",
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.1,
            "num_predict": 32,
        },
    }
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8", "replace"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
    except URLError as exc:
        raise RuntimeError(f"URL error: {exc.reason}") from exc
    return str(payload.get("response") or "").strip()


def _entity_rows(entity_master: Any) -> list[tuple[str, dict]]:
    if isinstance(entity_master, dict):
        if "items" in entity_master and isinstance(entity_master.get("items"), list):
            rows: list[tuple[str, dict]] = []
            for row in entity_master.get("items") or []:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("ticker") or row.get("symbol") or "").strip().upper()
                if symbol:
                    rows.append((symbol, row))
            return rows
        return [(str(symbol).strip().upper(), rec) for symbol, rec in entity_master.items() if isinstance(rec, dict)]
    return []


def _load_unknown_candidates(entity_master: Any, cache_symbols: dict[str, dict], limit: int, force: bool) -> list[tuple[str, dict]]:
    candidates: list[tuple[tuple[Any, ...], str, dict]] = []
    for symbol, rec in _entity_rows(entity_master):
        if _normalized_sector(rec) != "unknown":
            continue
        if not force and isinstance(cache_symbols.get(symbol), dict) and cache_symbols[symbol].get("sector"):
            continue
        priority = (
            symbol.endswith("F") or symbol.endswith("Y"),
            rec.get("etf") is True,
            -(float(rec.get("gravity") or 0.0)),
            not bool(rec.get("cik")),
            len(symbol),
            symbol,
        )
        candidates.append((priority, symbol, rec))
    candidates.sort(key=lambda item: item[0])
    rows = [(symbol, rec) for _, symbol, rec in candidates]
    return rows[:limit] if limit > 0 else rows


def _latency_summary(latencies: list[float]) -> dict[str, float]:
    if not latencies:
        return {}
    ordered = sorted(latencies)
    def _percentile(p: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * p)))
        return ordered[idx]
    return {
        "avg_seconds": round(statistics.fmean(ordered), 3),
        "p50_seconds": round(_percentile(0.5), 3),
        "p90_seconds": round(_percentile(0.9), 3),
        "max_seconds": round(max(ordered), 3),
    }


def _sanitize_cache_symbols(payload: dict[str, Any]) -> dict[str, dict]:
    raw = payload.get("symbols")
    if not isinstance(raw, dict):
        return {}
    cleaned: dict[str, dict] = {}
    for symbol, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        sector = str(entry.get("sector") or "").strip().lower()
        if not sector or sector == "unknown":
            continue
        bucket = _normalize_generic_bucket(entry.get("generic_bucket"))
        try:
            confidence = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        source = str(entry.get("source") or "").strip().lower()
        keep = True
        if source == "ollama_burnin":
            keep = bucket in GENERIC_BUCKET_TO_SECTOR or confidence >= 0.64 or str(entry.get("decision") or "").strip().lower() == "infer"
        if not keep:
            continue
        cleaned[str(symbol).strip().upper()] = entry
    return cleaned


def _should_accept(sector: str, bucket: str, confidence: float, min_confidence: float) -> bool:
    if bucket in METADATA_ONLY_BUCKETS:
        return False
    if bucket in GENERIC_BUCKET_TO_SECTOR:
        return True
    return sector != "unknown" and confidence >= min_confidence


def _write_status(path: Path, *, started_at: str, model: str, total_candidates: int, processed_count: int,
                  accepted_count: int, unresolved_count: int, error_count: int, latest: dict[str, Any] | None,
                  latencies: list[float]) -> None:
    payload = {
        "started_at": started_at,
        "updated_at": _iso_now(),
        "model": model,
        "total_candidates": total_candidates,
        "processed_count": processed_count,
        "accepted_count": accepted_count,
        "unresolved_count": unresolved_count,
        "error_count": error_count,
        "latency": _latency_summary(latencies),
        "latest": latest or {},
    }
    _write_json(path, payload)


def run(args: argparse.Namespace) -> int:
    entity_master = _read_json(ENTITY_MASTER_PATH, {})
    if not isinstance(entity_master, dict) or not entity_master:
        print("phase4_long_tail_burnin: entity_master.json unavailable")
        return 1

    cache_payload = _read_json(Path(args.cache), {"metadata": {}, "symbols": {}})
    if not isinstance(cache_payload, dict):
        cache_payload = {"metadata": {}, "symbols": {}}
    cache_symbols = _sanitize_cache_symbols(cache_payload)
    cache_payload["symbols"] = cache_symbols

    company_cache = _read_json(Path(args.company_cache), {})
    if not isinstance(company_cache, dict):
        company_cache = {}

    candidates = _load_unknown_candidates(entity_master, cache_symbols, args.limit, args.force)
    started_at = _iso_now()
    output_results: list[dict[str, Any]] = []
    latencies: list[float] = []
    accepted = 0
    unresolved = 0
    error_count = 0

    if not candidates:
        summary = {
            "started_at": started_at,
            "completed_at": _iso_now(),
            "model": args.model,
            "candidate_count": 0,
            "accepted_count": 0,
            "unresolved_count": 0,
            "error_count": 0,
            "latency": {},
            "ollama_base_url": args.ollama_base_url,
            "results": [],
        }
        _write_json(Path(args.output), summary)
        _write_status(
            Path(args.status_output),
            started_at=started_at,
            model=args.model,
            total_candidates=0,
            processed_count=0,
            accepted_count=0,
            unresolved_count=0,
            error_count=0,
            latest=None,
            latencies=[],
        )
        return 0

    _write_status(
        Path(args.status_output),
        started_at=started_at,
        model=args.model,
        total_candidates=len(candidates),
        processed_count=0,
        accepted_count=0,
        unresolved_count=0,
        error_count=0,
        latest=None,
        latencies=[],
    )

    for index, (symbol, rec) in enumerate(candidates, start=1):
        sec_info = _fetch_sec_company_info(str(rec.get("cik") or ""), company_cache) if args.include_sec else {}
        heuristic_bucket = _heuristic_bucket(symbol, rec.get("name") or sec_info.get("name") or "")
        before = _system_snapshot()
        started_at_symbol = _iso_now()
        started = time.time()
        error_text = ""
        raw_response = ""
        parsed: dict[str, Any] = {}
        if heuristic_bucket in GENERIC_BUCKET_TO_SECTOR:
            parsed = {
                "sector": GENERIC_BUCKET_TO_SECTOR[heuristic_bucket],
                "confidence": 1.0,
                "generic_bucket": heuristic_bucket,
                "classification": str(rec.get("name") or sec_info.get("name") or symbol),
                "reason": f"deterministic heuristic bucket: {heuristic_bucket}",
            }
            latency = round(time.time() - started, 3)
        else:
            _wait_for_budget(args.max_load1, args.max_mem_used_pct, args.cooldown_seconds)
            system, user = _build_prompt(symbol, rec, sec_info)
            started = time.time()
            try:
                raw_response = _call_ollama(args.ollama_base_url, args.api_key, args.model, system, user, args.timeout_seconds)
            except Exception as exc:
                error_text = str(exc)
            latency = round(time.time() - started, 3)
            parsed = _extract_json_block(raw_response)
        after = _system_snapshot()
        latencies.append(latency)

        bucket = _normalize_generic_bucket(parsed.get("generic_bucket") or heuristic_bucket)
        sector = _normalize_sector(parsed.get("sector"), bucket)
        classification = str(parsed.get("classification") or "").strip() or str(rec.get("name") or symbol)
        reason = str(parsed.get("reason") or error_text or "").strip()
        try:
            confidence = round(max(0.0, min(1.0, float(parsed.get("confidence", 0.0)))), 3)
        except (TypeError, ValueError):
            confidence = 0.0
        accepted_sector = _should_accept(sector, bucket, confidence, args.min_confidence)
        if error_text:
            status = "error"
        elif accepted_sector:
            status = "accepted"
        elif bucket in METADATA_ONLY_BUCKETS:
            status = "metadata_only"
        else:
            status = "review"
        if status == "accepted":
            accepted += 1
        else:
            unresolved += 1
        if status == "error":
            error_count += 1

        result = {
            "symbol": symbol,
            "name": rec.get("name") or sec_info.get("name") or symbol,
            "status": status,
            "sector": sector,
            "generic_bucket": bucket,
            "confidence": confidence,
            "classification": classification,
            "reason": reason,
            "latency_seconds": latency,
            "system_before": before,
            "system_after": after,
            "raw_response": raw_response[:600],
            "error": error_text,
        }
        output_results.append(result)

        if status == "accepted":
            cache_symbols[symbol] = {
                "sector": sector if sector != "unknown" else "",
                "generic_bucket": bucket,
                "classification": classification,
                "confidence": confidence,
                "source": "ollama_burnin",
                "model": args.model,
                "name": result["name"],
                "decision": "infer",
                "updated_at": started_at_symbol,
            }
            if args.write_cache:
                _write_json(Path(args.cache), cache_payload)
        elif isinstance(cache_symbols.get(symbol), dict) and cache_symbols[symbol].get("source") == "ollama_burnin":
            cache_symbols.pop(symbol, None)
        if args.save_company_cache:
            _write_json(Path(args.company_cache), company_cache)

        _write_status(
            Path(args.status_output),
            started_at=started_at,
            model=args.model,
            total_candidates=len(candidates),
            processed_count=index,
            accepted_count=accepted,
            unresolved_count=unresolved,
            error_count=error_count,
            latest=result,
            latencies=latencies,
        )

        print(f"[{index}/{len(candidates)}] {symbol} -> {sector} ({status}, {latency:.2f}s)", flush=True)
        time.sleep(max(0.0, args.cooldown_seconds))

    summary = {
        "started_at": started_at,
        "completed_at": _iso_now(),
        "model": args.model,
        "candidate_count": len(candidates),
        "accepted_count": accepted,
        "unresolved_count": unresolved,
        "error_count": error_count,
        "latency": _latency_summary(latencies),
        "ollama_base_url": args.ollama_base_url,
        "results": output_results,
    }
    _write_json(Path(args.output), summary)
    if args.write_cache:
        cache_payload["metadata"] = {
            "updated_at": summary["completed_at"],
            "model": args.model,
            "accepted_count": accepted,
            "candidate_count": len(candidates),
            "cached_symbol_count": len(cache_symbols),
        }
        _write_json(Path(args.cache), cache_payload)
    if args.save_company_cache:
        _write_json(Path(args.company_cache), company_cache)
    _write_status(
        Path(args.status_output),
        started_at=started_at,
        model=args.model,
        total_candidates=len(candidates),
        processed_count=len(candidates),
        accepted_count=accepted,
        unresolved_count=unresolved,
        error_count=error_count,
        latest=output_results[-1] if output_results else None,
        latencies=latencies,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a throttled Ollama burn-in against unknown universe symbols.")
    parser.add_argument("--limit", type=int, default=10, help="Number of unknown symbols to process. Use 0 for all.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model name.")
    parser.add_argument("--ollama-base-url", default=DEFAULT_OLLAMA_BASE_URL, help="OpenAI-compatible Ollama base URL.")
    parser.add_argument("--api-key", default=DEFAULT_OLLAMA_API_KEY, help="API key for the OpenAI-compatible Ollama endpoint.")
    parser.add_argument("--timeout-seconds", type=float, default=120.0, help="Timeout per model request.")
    parser.add_argument("--min-confidence", type=float, default=0.64, help="Minimum confidence for accepted classifications.")
    parser.add_argument("--cooldown-seconds", type=float, default=0.2, help="Delay between requests.")
    parser.add_argument("--max-load1", type=float, default=3.0, help="Pause if 1-minute load average exceeds this.")
    parser.add_argument("--max-mem-used-pct", type=float, default=88.0, help="Pause if memory used percent exceeds this.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Path to write the run report.")
    parser.add_argument("--status-output", default=str(DEFAULT_STATUS_PATH), help="Path to write the live progress status.")
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH), help="Path to write accepted long-tail sector cache entries.")
    parser.add_argument("--company-cache", default=str(DEFAULT_COMPANY_INFO_CACHE), help="Path for cached SEC company info.")
    parser.add_argument("--force", action="store_true", help="Reprocess symbols even if they already have cache entries.")
    parser.add_argument("--include-sec", action="store_true", help="Fetch SEC company info to enrich prompts.")
    parser.add_argument("--write-cache", action="store_true", help="Persist accepted classifications into the cache file.")
    parser.add_argument("--save-company-cache", action="store_true", help="Persist SEC company info cache.")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
