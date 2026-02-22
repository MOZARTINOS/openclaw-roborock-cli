"""Authentication flow for Roborock Cloud API."""

from __future__ import annotations

import hashlib
import secrets

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
    params: dict | None = None,
    headers: dict | None = None,
) -> dict:
    """Perform an HTTP request and return decoded JSON payload."""
    async with session.request(method, url, params=params, headers=headers) as response:
        response.raise_for_status()
        data = await response.json(content_type=None)
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected API response from {url}")
        return data


def _build_header_clientid(email: str, device_id: str) -> str:
    """Build header_clientid value used by Roborock auth endpoints."""
    return hashlib.md5((email + "should_be_unique" + device_id).encode()).hexdigest()


async def discover_region(email: str) -> dict:
    """Discover the correct API region for an email address."""
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

            if data.get("code") == 200 and data.get("data"):
                region_data = data["data"]
                return {
                    "base_url": region_data["url"],
                    "country": region_data.get("country", "Unknown"),
                    "country_code": region_data.get("countrycode", ""),
                }

    raise RuntimeError("Could not find Roborock region for this email")


async def request_code(email: str, base_url: str) -> None:
    """Request a verification code to be sent to the email."""
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


async def login_with_code(email: str, code: str, base_url: str) -> dict:
    """Login with verification code and return full user data including rriot."""
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

    return data["data"]


async def get_home_data(user_data: dict) -> dict:
    """Fetch home data (devices, rooms) from the cloud API."""
    rriot = user_data["rriot"]
    base_url = rriot["r"]["a"].rstrip("/")
    token = user_data["token"]

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        data = await _request_json(
            session,
            "GET",
            f"{base_url}/api/v1/getHomeDetail",
            headers={"Authorization": token},
        )

    if data.get("code") != 200 and not data.get("success"):
        raise RuntimeError(f"Failed to get home data: {data}")

    return data.get("data", data.get("result", {}))


def build_config(email: str, user_data: dict, home_data: dict) -> dict:
    """Build a config dict from login and home data."""
    devices = home_data.get("devices", [])
    products = home_data.get("products", [])

    product_map = {product["id"]: product for product in products if "id" in product}

    config: dict = {
        "email": email,
        "rriot": user_data["rriot"],
        "devices": [],
    }

    for dev in devices:
        product = product_map.get(dev.get("product_id", ""), {})
        config["devices"].append(
            {
                "duid": dev["duid"],
                "name": dev.get("name", "Unknown"),
                "local_key": dev["local_key"],
                "product_id": dev.get("product_id", ""),
                "model": product.get("model", "unknown"),
                "online": dev.get("online", False),
            }
        )

    return config
