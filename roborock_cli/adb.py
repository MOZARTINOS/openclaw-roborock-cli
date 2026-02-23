"""ADB extraction helpers for Roborock login payload and config setup."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import aiohttp

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
LOGIN_MARKER = "FeatureCacheService->loadLoginResponse"


def _decode_json_candidate(candidate: str) -> dict[str, Any] | None:
    """Decode a potential login JSON payload candidate."""
    parsers = (
        lambda s: json.loads(s),
        lambda s: json.loads(bytes(s, "utf-8").decode("unicode_escape")),
    )
    for parse in parsers:
        try:
            payload = parse(candidate)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _extract_payload_from_line(line: str) -> dict[str, Any] | None:
    """Extract login payload from a single log line."""
    if LOGIN_MARKER not in line:
        return None

    candidates: list[str] = []

    start = line.find('"{\\')
    end = line.rfind('}"')
    if start != -1 and end != -1 and end > start:
        candidates.append(line[start + 1 : end + 1])

    pattern = re.compile(r'"(\{\\.*\})"')
    for match in pattern.finditer(line):
        candidates.append(match.group(1))

    for candidate in candidates:
        payload = _decode_json_candidate(candidate)
        if payload and payload.get("rriot") and payload.get("token"):
            return payload

    return None


def normalize_extracted_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize extracted payload and validate required keys."""
    required_top = ("token", "uid", "rruid", "rriot")
    for key in required_top:
        if key not in payload:
            raise RuntimeError(f"Extracted payload missing required field: {key}")

    rriot = payload.get("rriot")
    if not isinstance(rriot, dict):
        raise RuntimeError("Extracted payload field 'rriot' must be an object")

    required_rriot = ("u", "s", "h", "k", "r")
    for key in required_rriot:
        if key not in rriot:
            raise RuntimeError(f"Extracted payload missing rriot.{key}")

    ref = rriot.get("r")
    if not isinstance(ref, dict):
        raise RuntimeError("Extracted payload field 'rriot.r' must be an object")

    for key in ("a", "m", "l", "r"):
        if key not in ref:
            raise RuntimeError(f"Extracted payload missing rriot.r.{key}")

    return {
        "token": payload.get("token"),
        "uid": payload.get("uid"),
        "rruid": payload.get("rruid"),
        "region": payload.get("region"),
        "country": payload.get("country"),
        "nickname": payload.get("nickname"),
        "rriot": payload.get("rriot"),
    }


def extract_payload_from_log(log_path: Path) -> dict[str, Any]:
    """Extract normalized login payload from a logcat capture file."""
    if not log_path.exists():
        raise RuntimeError(f"Log file not found: {log_path}")

    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        payload = _extract_payload_from_line(line)
        if payload:
            return normalize_extracted_payload(payload)

    raise RuntimeError(
        "No login payload found in log. Look for FeatureCacheService->loadLoginResponse in logcat output."
    )


def load_extracted_payload(extracted_path: Path) -> dict[str, Any]:
    """Load and validate an extracted payload JSON file."""
    if not extracted_path.exists():
        raise RuntimeError(f"Extracted JSON file not found: {extracted_path}")

    try:
        payload = json.loads(extracted_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid extracted JSON: {error}") from error

    if not isinstance(payload, dict):
        raise RuntimeError("Extracted JSON root must be an object")

    return normalize_extracted_payload(payload)


def save_extracted_payload(payload: dict[str, Any], output_path: Path) -> Path:
    """Write normalized extracted payload to disk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


async def get_home_data_from_token(token: str, api_base: str) -> dict[str, Any]:
    """Fetch home data using token + API base URL from extracted login payload."""
    url = f"{api_base.rstrip('/')}/api/v1/getHomeDetail"

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.get(url, headers={"Authorization": token}) as response:
            response.raise_for_status()
            data = await response.json(content_type=None)

    if not isinstance(data, dict):
        raise RuntimeError("Unexpected response format from getHomeDetail")

    if data.get("code") != 200 and not data.get("success"):
        raise RuntimeError(f"Failed to get home data: {data}")

    return data.get("data", data.get("result", {}))


def redact_secret(value: str, keep: int = 4) -> str:
    """Redact a secret for console-safe display."""
    if len(value) <= keep * 2:
        return "*" * max(8, len(value))
    return f"{value[:keep]}...{value[-keep:]}"
