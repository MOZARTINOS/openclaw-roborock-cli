import json
from pathlib import Path

import pytest

from roborock_cli.adb import extract_payload_from_log, load_extracted_payload, save_extracted_payload


def _sample_payload() -> dict:
    return {
        "token": "rr1234567890:abc:def",
        "uid": 123456,
        "rruid": "rr1234567890",
        "region": "eu",
        "country": "NO",
        "nickname": "Tester",
        "rriot": {
            "u": "user_u",
            "s": "secret_s",
            "h": "secret_h",
            "k": "secret_k",
            "r": {
                "a": "https://api-eu.roborock.com",
                "m": "ssl://mqtt-eu-2.roborock.com:8883",
                "l": "https://wood-eu.roborock.com",
                "r": "EU",
            },
        },
    }


def test_extract_payload_from_log_parses_login_line(tmp_path: Path) -> None:
    payload = _sample_payload()
    escaped = json.dumps(payload).replace('"', '\\"')
    line = (
        "02-22 16:51:14.496 24665 26080 I ReactNativeJS: "
        "'FeatureCacheService->loadLoginResponse', "
        f"'\"{escaped}\"'"
    )
    path = tmp_path / "roborock_log.txt"
    path.write_text(line + "\n", encoding="utf-8")

    extracted = extract_payload_from_log(path)

    assert extracted["token"] == payload["token"]
    assert extracted["rruid"] == payload["rruid"]
    assert extracted["rriot"]["r"]["a"] == "https://api-eu.roborock.com"


def test_load_extracted_payload_requires_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"token": "x"}), encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_extracted_payload(path)


def test_save_extracted_payload_roundtrip(tmp_path: Path) -> None:
    payload = _sample_payload()
    path = tmp_path / "roborock_extracted.json"

    saved = save_extracted_payload(payload, path)
    loaded = load_extracted_payload(path)

    assert saved == path
    assert loaded["token"] == payload["token"]
