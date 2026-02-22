"""Authentication flow for Roborock Cloud API."""

import asyncio
import hashlib
import json
import secrets

import aiohttp

# Roborock IoT base URLs to try
BASE_URLS = [
    "https://euiot.roborock.com",
    "https://usiot.roborock.com",
    "https://cniot.roborock.com",
]


async def discover_region(email: str) -> dict:
    """Discover the correct API region for an email address."""
    async with aiohttp.ClientSession() as session:
        for base_url in BASE_URLS:
            try:
                resp = await session.post(
                    f"{base_url}/api/v1/getUrlByEmail",
                    params={"email": email, "needtwostepauth": "false"},
                )
                data = await resp.json()
                if data.get("code") == 200:
                    return {
                        "base_url": data["data"]["url"],
                        "country": data["data"]["country"],
                        "country_code": data["data"]["countrycode"],
                    }
            except Exception:
                continue
    raise RuntimeError("Could not find Roborock region for this email")


async def request_code(email: str, base_url: str) -> None:
    """Request a verification code to be sent to the email."""
    device_id = secrets.token_urlsafe(16)
    header_clientid = hashlib.md5(
        (email + "should_be_unique" + device_id).encode()
    ).hexdigest()

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"{base_url}/api/v1/sendEmailCode",
            params={"username": email, "type": "auth"},
            headers={"header_clientid": header_clientid},
        )
        data = await resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"Failed to send code: {data.get('msg', 'Unknown error')}")


async def login_with_code(email: str, code: str, base_url: str) -> dict:
    """Login with verification code and return full user data including rriot."""
    device_id = secrets.token_urlsafe(16)
    header_clientid = hashlib.md5(
        (email + "should_be_unique" + device_id).encode()
    ).hexdigest()

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"{base_url}/api/v1/loginWithCode",
            params={
                "username": email,
                "verifycode": code,
                "verifycodetype": "AUTH_EMAIL_CODE",
            },
            headers={"header_clientid": header_clientid},
        )
        data = await resp.json()

        response_code = data.get("code")
        if response_code == 2018:
            raise RuntimeError("Invalid verification code. Check and try again.")
        if response_code != 200:
            raise RuntimeError(f"Login failed: {data.get('msg', 'Unknown error')} (code {response_code})")

        return data["data"]


async def get_home_data(user_data: dict) -> dict:
    """Fetch home data (devices, rooms) from the cloud API."""
    rriot = user_data["rriot"]
    base_url = rriot["r"]["a"]
    token = user_data["token"]

    async with aiohttp.ClientSession() as session:
        # Get home ID
        resp = await session.get(
            f"{base_url}/api/v1/getHomeDetail",
            headers={"Authorization": token},
        )
        data = await resp.json()
        if data.get("code") != 200 and not data.get("success"):
            raise RuntimeError(f"Failed to get home data: {data}")
        return data.get("data", data.get("result", {}))


def build_config(email: str, user_data: dict, home_data: dict) -> dict:
    """Build a config dict from login and home data."""
    devices = home_data.get("devices", [])
    products = home_data.get("products", [])

    # Build product lookup
    product_map = {p["id"]: p for p in products}

    config = {
        "email": email,
        "rriot": user_data["rriot"],
        "devices": [],
    }

    for dev in devices:
        product = product_map.get(dev.get("product_id", ""), {})
        config["devices"].append({
            "duid": dev["duid"],
            "name": dev.get("name", "Unknown"),
            "local_key": dev["local_key"],
            "product_id": dev.get("product_id", ""),
            "model": product.get("model", "unknown"),
            "online": dev.get("online", False),
        })

    return config
