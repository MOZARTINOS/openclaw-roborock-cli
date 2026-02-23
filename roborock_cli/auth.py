"""Authentication flow for Roborock Cloud API."""

from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
import time
from typing import Any

import aiohttp

# Roborock IoT base URLs to try.
BASE_URLS = [
    "https://euiot.roborock.com",
    "https://usiot.roborock.com",
    "https://cniot.roborock.com",
]

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)


async def _request_json(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Perform an HTTP request and decode a JSON object response."""
    async with session.request(method, url, params=params, headers=headers) as response:
        response.raise_for_status()
        payload = await response.json(content_type=None)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected API response from {url}")
    return payload


def _build_header_clientid(email: str, device_id: str) -> str:
    return hashlib.md5((email + "should_be_unique" + device_id).encode()).hexdigest()


async def discover_region(email: str) -> dict[str, str]:
    """Discover API region for an email address."""
    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        for base_url in BASE_URLS:
            try:
                data = await _request_json(
                    session,
                    "POST",
                    f"{base_url}/api/v1/getUrlByEmail",
                    params={"email": email, "needtwostepauth": "false"},
                )
            except (aiohttp.ClientError, RuntimeError, ValueError):
                continue

            if data.get("code") == 200 and isinstance(data.get("data"), dict):
                region_data = data["data"]
                return {
                    "base_url": str(region_data.get("url", base_url)).rstrip("/"),
                    "country": str(region_data.get("country", "Unknown")),
                    "country_code": str(region_data.get("countrycode", "")),
                }

    raise RuntimeError("Could not find Roborock region for this email")


async def request_code(email: str, base_url: str) -> None:
    """Request email verification code."""
    device_id = secrets.token_urlsafe(16)
    header_clientid = _build_header_clientid(email, device_id)

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        data = await _request_json(
            session,
            "POST",
            f"{base_url.rstrip('/')}/api/v1/sendEmailCode",
            params={"username": email, "type": "auth"},
            headers={"header_clientid": header_clientid},
        )

    if data.get("code") != 200:
        raise RuntimeError(f"Failed to send code: {data.get('msg', 'Unknown error')}")


async def login_with_code(email: str, code: str, base_url: str) -> dict[str, Any]:
    """Login via email verification code and return user payload (includes rriot)."""
    device_id = secrets.token_urlsafe(16)
    header_clientid = _build_header_clientid(email, device_id)

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        data = await _request_json(
            session,
            "POST",
            f"{base_url.rstrip('/')}/api/v1/loginWithCode",
            params={
                "username": email,
                "verifycode": code,
                "verifycodetype": "AUTH_EMAIL_CODE",
            },
            headers={"header_clientid": header_clientid},
        )

    response_code = data.get("code")
    if response_code == 2018:
        raise RuntimeError("Invalid verification code. Check and try again.")
    if response_code != 200:
        raise RuntimeError(
            f"Login failed: {data.get('msg', 'Unknown error')} (code {response_code})"
        )

    user_data = data.get("data")
    if not isinstance(user_data, dict):
        raise RuntimeError("Login succeeded but response payload is missing data")
    return user_data


def _hawk_auth(rriot: dict[str, Any], url_path: str) -> str:
    """Build Hawk auth header for cloud API routes."""
    timestamp = math.floor(time.time())
    nonce = secrets.token_urlsafe(6)
    prestr = ":".join(
        [
            str(rriot["u"]),
            str(rriot["s"]),
            nonce,
            str(timestamp),
            hashlib.md5(url_path.encode()).hexdigest(),
            "",
            "",
        ]
    )
    mac = base64.b64encode(
        hmac.new(str(rriot["h"]).encode(), prestr.encode(), hashlib.sha256).digest()
    ).decode()
    return f'Hawk id="{rriot["u"]}",s="{rriot["s"]}",ts="{timestamp}",nonce="{nonce}",mac="{mac}"'


async def get_home_id(user_data: dict[str, Any]) -> int:
    """Resolve Roborock home ID via token-auth endpoint."""
    token = user_data["token"]
    rriot = user_data["rriot"]
    ref = rriot["r"]
    header_clientid = hashlib.md5(str(rriot["u"]).encode()).hexdigest()

    region_code = str(ref.get("r", "")).lower()
    api_base = str(ref.get("a", "")).rstrip("/")
    endpoints = [
        f"https://{region_code}iot.roborock.com" if region_code else "",
        api_base,
    ]

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        for base in [endpoint for endpoint in endpoints if endpoint]:
            try:
                data = await _request_json(
                    session,
                    "GET",
                    f"{base}/api/v1/getHomeDetail",
                    headers={
                        "Authorization": token,
                        "header_clientid": header_clientid,
                    },
                )
            except (aiohttp.ClientError, RuntimeError, ValueError):
                continue

            if data.get("code") == 200 and isinstance(data.get("data"), dict):
                home_id = data["data"].get("rrHomeId")
                if isinstance(home_id, int):
                    return home_id

    raise RuntimeError("Failed to get home ID from cloud API")


async def _get_home_data_token(user_data: dict[str, Any]) -> dict[str, Any]:
    """Fallback home-data fetch using token-auth endpoint."""
    token = user_data["token"]
    api_base = str(user_data["rriot"]["r"]["a"]).rstrip("/")

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        data = await _request_json(
            session,
            "GET",
            f"{api_base}/api/v1/getHomeDetail",
            headers={"Authorization": token},
        )

    if data.get("code") != 200 and not data.get("success"):
        raise RuntimeError(f"Failed to get home data: {data}")

    payload = data.get("data", data.get("result", {}))
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected home-data payload")
    return payload


async def get_home_data(user_data: dict[str, Any]) -> dict[str, Any]:
    """Fetch home data (devices/products/rooms) from Roborock cloud."""
    rriot = user_data["rriot"]
    api_base = str(rriot["r"]["a"]).rstrip("/")

    try:
        home_id = await get_home_id(user_data)
        url_path = f"/user/homes/{home_id}"
        hawk = _hawk_auth(rriot, url_path)

        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            data = await _request_json(
                session,
                "GET",
                f"{api_base}{url_path}",
                headers={"Authorization": hawk},
            )

        if data.get("success"):
            payload = data.get("result", {})
            if isinstance(payload, dict):
                return payload
    except Exception:
        # Fall back to token endpoint if Hawk route fails for any reason.
        pass

    return await _get_home_data_token(user_data)


def build_config(email: str, user_data: dict[str, Any], home_data: dict[str, Any]) -> dict[str, Any]:
    """Build persisted CLI config from auth and home data."""
    devices = home_data.get("devices", [])
    products = home_data.get("products", [])
    rooms = home_data.get("rooms", [])

    product_map = {product["id"]: product for product in products if isinstance(product, dict) and "id" in product}

    config: dict[str, Any] = {
        "email": email,
        "rriot": user_data["rriot"],
        "devices": [],
        "rooms": {
            str(room["id"]): str(room.get("name", f"Room {room['id']}"))
            for room in rooms
            if isinstance(room, dict) and "id" in room
        },
    }

    for device in devices:
        if not isinstance(device, dict) or "duid" not in device:
            continue

        product_id = device.get("product_id", device.get("productId", ""))
        product = product_map.get(product_id, {})
        config["devices"].append(
            {
                "duid": device["duid"],
                "name": device.get("name", "Unknown"),
                "local_key": device.get("local_key", device.get("localKey", "")),
                "product_id": product_id,
                "model": product.get("model", "unknown"),
                "online": device.get("online", False),
            }
        )

    return config
