"""Authentication flow for Roborock Cloud API."""

import asyncio
import base64
import hashlib
import hmac
import json
import math
import secrets
import time

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


def _hawk_auth(rriot: dict, url_path: str) -> str:
    """Generate Hawk authentication header for Roborock API."""
    timestamp = math.floor(time.time())
    nonce = secrets.token_urlsafe(6)
    prestr = ":".join([
        rriot["u"], rriot["s"], nonce, str(timestamp),
        hashlib.md5(url_path.encode()).hexdigest(),
        "",  # params
        "",  # formdata
    ])
    mac = base64.b64encode(
        hmac.new(rriot["h"].encode(), prestr.encode(), hashlib.sha256).digest()
    ).decode()
    return f'Hawk id="{rriot["u"]}",s="{rriot["s"]}",ts="{timestamp}",nonce="{nonce}",mac="{mac}"'


async def get_home_id(user_data: dict) -> int:
    """Get the Roborock home ID from the cloud."""
    token = user_data["token"]
    rriot = user_data["rriot"]
    header_clientid = hashlib.md5(rriot["u"].encode()).hexdigest()

    # Try the IoT endpoint first (more reliable for getHomeDetail)
    iot_base = rriot["r"]["a"].replace("api-", "").replace(".roborock.com", "iot.roborock.com")
    # Fallback list
    urls_to_try = [
        f"https://{rriot['r']['r'].lower()}iot.roborock.com",
        rriot["r"]["a"],
    ]

    async with aiohttp.ClientSession() as session:
        for base in urls_to_try:
            try:
                resp = await session.get(
                    f"{base}/api/v1/getHomeDetail",
                    headers={
                        "Authorization": token,
                        "header_clientid": header_clientid,
                    },
                )
                data = await resp.json()
                if data.get("code") == 200:
                    return data["data"]["rrHomeId"]
            except Exception:
                continue

    raise RuntimeError("Failed to get home ID from any endpoint")


async def get_home_data(user_data: dict) -> dict:
    """Fetch home data (devices, rooms) from the cloud API."""
    rriot = user_data["rriot"]
    api_base = rriot["r"]["a"]

    home_id = await get_home_id(user_data)
    url_path = f"/user/homes/{home_id}"
    hawk = _hawk_auth(rriot, url_path)

    async with aiohttp.ClientSession() as session:
        resp = await session.get(
            f"{api_base}{url_path}",
            headers={"Authorization": hawk},
        )
        data = await resp.json()
        if not data.get("success"):
            raise RuntimeError(f"Failed to get home data: {data}")
        return data.get("result", {})


async def get_room_names(user_data: dict) -> dict[str, str]:
    """Fetch room name mapping from the cloud: {cloud_id: name}.

    This maps the cloud room IDs to human-readable names set in the Roborock app.
    Combine with get_room_mapping device command to map segment_id → room name.
    """
    home_data = await get_home_data(user_data)
    rooms = home_data.get("rooms", [])
    return {str(r["id"]): r["name"] for r in rooms}


def build_config(email: str, user_data: dict, home_data: dict) -> dict:
    """Build a config dict from login and home data."""
    devices = home_data.get("devices", [])
    products = home_data.get("products", [])
    rooms = home_data.get("rooms", [])

    # Build product lookup
    product_map = {p["id"]: p for p in products}

    config = {
        "email": email,
        "rriot": user_data["rriot"],
        "devices": [],
        "rooms": {str(r["id"]): r["name"] for r in rooms},
    }

    for dev in devices:
        product = product_map.get(dev.get("product_id", dev.get("productId", "")), {})
        config["devices"].append({
            "duid": dev["duid"],
            "name": dev.get("name", "Unknown"),
            "local_key": dev.get("local_key", dev.get("localKey", "")),
            "product_id": dev.get("product_id", dev.get("productId", "")),
            "model": product.get("model", "unknown"),
            "online": dev.get("online", False),
        })

    return config
