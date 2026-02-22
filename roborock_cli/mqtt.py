"""MQTT connection and command sending for Roborock devices."""

import asyncio
import json
import logging

from roborock.data.containers import HomeDataDevice, Reference, RRiot
from roborock.devices.rpc.v1_channel import RpcChannel, RpcStrategy
from roborock.devices.transport.mqtt_channel import MqttChannel
from roborock.mqtt.roborock_session import RoborockMqttSession
from roborock.mqtt.session import MqttParams
from roborock.protocol import create_mqtt_params
from roborock.protocols.v1_protocol import (
    RequestMessage,
    create_security_data,
    decode_rpc_response,
)
from roborock.roborock_message import RoborockMessageProtocol
from roborock.roborock_typing import RoborockCommand
from roborock.util import RoborockLoggerAdapter

logger = logging.getLogger(__name__)


def build_rriot(config: dict) -> RRiot:
    """Build RRiot object from config dict."""
    r = config["rriot"]
    return RRiot(
        u=r["u"],
        s=r["s"],
        h=r["h"],
        k=r["k"],
        r=Reference(
            r=r["r"]["r"],
            a=r["r"]["a"],
            m=r["r"]["m"],
            l=r["r"]["l"],
        ),
    )


def build_device(device_config: dict) -> HomeDataDevice:
    """Build HomeDataDevice from config dict."""
    return HomeDataDevice(
        duid=device_config["duid"],
        name=device_config.get("name", "Roborock"),
        local_key=device_config["local_key"],
        product_id=device_config.get("product_id", ""),
    )


async def send_command(
    config: dict,
    command: RoborockCommand,
    params: list | dict | None = None,
    device_index: int = 0,
) -> any:
    """Connect to MQTT, send a command, and return the result."""
    rriot = build_rriot(config)

    devices = config.get("devices", [])
    if not devices:
        # Fallback: single device config (legacy format)
        device_config = config.get("device", {})
    else:
        if device_index >= len(devices):
            raise ValueError(f"Device index {device_index} out of range (have {len(devices)} devices)")
        device_config = devices[device_index]

    device = build_device(device_config)
    mqtt_params = create_mqtt_params(rriot)
    security_data = create_security_data(rriot)

    session = RoborockMqttSession(mqtt_params)

    try:
        await session.start()

        channel = MqttChannel(session, device.duid, device.local_key, rriot, mqtt_params)

        log_adapter = RoborockLoggerAdapter(duid=device.duid, logger=logger)

        def encoder(req: RequestMessage):
            return req.encode_message(
                RoborockMessageProtocol.RPC_REQUEST,
                security_data=security_data,
            )

        strategy = RpcStrategy(
            name="mqtt",
            channel=channel,
            encoder=encoder,
            decoder=decode_rpc_response,
            health_manager=channel.health_manager,
        )

        rpc = RpcChannel(lambda: [strategy], log_adapter)
        return await rpc.send_command(command, params=params)
    finally:
        await session.close()
