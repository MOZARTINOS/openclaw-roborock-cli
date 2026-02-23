"""Camera livestream via WebRTC for Roborock vacuums with cameras.

Supported models: S8 MaxV, S8 Pro Ultra, Qrevo series, and other camera-equipped models.
NOT supported: Roborock S8 (standard), S7, S6, E-series.

Protocol:
1. Connect to MQTT (same as command control)
2. Authenticate with camera pattern password
3. Start camera preview session
4. Get TURN server credentials from Roborock cloud
5. Exchange SDP/ICE candidates via MQTT
6. Establish WebRTC peer connection
7. Receive video + audio tracks

Based on protocol documentation from python-roborock PR #764.
"""

import asyncio
import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import av
from aiortc import (
    MediaStreamTrack,
    RTCConfiguration,
    RTCIceCandidate,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
)
from aiortc.contrib.media import MediaRecorder

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
from roborock.util import RoborockLoggerAdapter

from .mqtt import build_device, build_rriot

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    """Camera session configuration."""
    pattern_password: str = ""
    quality: str = "HD"  # "HD" or "SD"
    device_index: int = 0


@dataclass
class CameraSession:
    """Active camera session state."""
    rpc: RpcChannel = None
    pc: RTCPeerConnection = None
    mqtt_session: RoborockMqttSession = None
    video_track: MediaStreamTrack = None
    audio_track: MediaStreamTrack = None
    running: bool = False
    frame_callback: Callable = None
    _latest_frame: any = None


class RoborockCamera:
    """Camera controller for Roborock vacuums with cameras.

    Usage:
        camera = RoborockCamera(config, camera_config)
        await camera.connect()
        frame = await camera.snapshot()
        await camera.disconnect()
    """

    def __init__(self, config: dict, camera_config: CameraConfig | None = None):
        self.config = config
        self.camera_config = camera_config or CameraConfig()
        self.session = CameraSession()
        self._setup_done = False

    async def connect(self) -> None:
        """Establish MQTT connection and WebRTC camera stream."""
        rriot = build_rriot(self.config)
        devices = self.config.get("devices", [])
        device_config = devices[self.camera_config.device_index] if devices else self.config.get("device", {})
        device = build_device(device_config)

        mqtt_params = create_mqtt_params(rriot)
        security_data = create_security_data(rriot)

        # Step 1: Connect MQTT
        logger.info("Connecting to MQTT...")
        self.session.mqtt_session = RoborockMqttSession(mqtt_params)
        await self.session.mqtt_session.start()

        channel = MqttChannel(self.session.mqtt_session, device.duid, device.local_key, rriot, mqtt_params)
        log_adapter = RoborockLoggerAdapter(duid=device.duid, logger=logger)

        def encoder(req: RequestMessage):
            return req.encode_message(
                RoborockMessageProtocol.RPC_REQUEST,
                security_data=security_data,
            )

        strategy = RpcStrategy(
            name="mqtt", channel=channel, encoder=encoder,
            decoder=decode_rpc_response, health_manager=channel.health_manager,
        )
        self.session.rpc = RpcChannel(lambda: [strategy], log_adapter)

        # Step 2: Authenticate camera password (if set)
        if self.camera_config.pattern_password:
            logger.info("Authenticating camera password...")
            pwd_hash = hashlib.md5(self.camera_config.pattern_password.encode()).hexdigest()
            try:
                await self.session.rpc.send_command(
                    "check_homesec_password", params={"password": pwd_hash}
                )
            except Exception as e:
                raise RuntimeError(f"Camera password authentication failed: {e}")

        # Step 3: Start camera preview
        logger.info("Starting camera preview...")
        client_id = f"roborock-cli-{int(time.time())}"
        try:
            await self.session.rpc.send_command(
                "start_camera_preview",
                params={
                    "client_id": client_id,
                    "quality": self.camera_config.quality,
                },
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to start camera preview: {e}\n"
                f"Make sure your vacuum model has a camera and close the Roborock app first."
            )

        # Step 4: Get TURN server
        logger.info("Getting TURN server credentials...")
        turn_data = await self.session.rpc.send_command("get_turn_server")
        logger.debug("TURN server: %s", turn_data)

        if isinstance(turn_data, list) and len(turn_data) > 0:
            turn_data = turn_data[0]

        turn_url = turn_data.get("url", "")
        turn_user = turn_data.get("user", "")
        turn_pwd = turn_data.get("pwd", "")

        # Step 5: Create WebRTC peer connection
        ice_servers = []
        if turn_url:
            ice_servers.append(RTCIceServer(
                urls=[turn_url],
                username=turn_user,
                credential=turn_pwd,
            ))

        rtc_config = RTCConfiguration(iceServers=ice_servers)
        self.session.pc = RTCPeerConnection(rtc_config)

        # Track handlers
        @self.session.pc.on("track")
        def on_track(track):
            logger.info("Received %s track", track.kind)
            if track.kind == "video":
                self.session.video_track = track
            elif track.kind == "audio":
                self.session.audio_track = track

        # Add transceivers for receiving media
        self.session.pc.addTransceiver("video", direction="recvonly")
        self.session.pc.addTransceiver("audio", direction="recvonly")

        # Step 6: Create and send SDP offer
        offer = await self.session.pc.createOffer()
        await self.session.pc.setLocalDescription(offer)

        sdp_json = json.dumps({"sdp": offer.sdp, "type": offer.type})
        sdp_b64 = base64.b64encode(sdp_json.encode()).decode()

        logger.info("Sending SDP offer...")
        await self.session.rpc.send_command(
            "send_sdp_to_robot", params={"app_sdp": sdp_b64}
        )

        # Step 7: Get device SDP answer (with retry)
        logger.info("Waiting for device SDP answer...")
        for attempt in range(10):
            try:
                sdp_result = await self.session.rpc.send_command("get_device_sdp")
                if isinstance(sdp_result, list) and len(sdp_result) > 0:
                    sdp_result = sdp_result[0]
                if isinstance(sdp_result, dict) and "dev_sdp" in sdp_result:
                    break
                if sdp_result == "retry" or (isinstance(sdp_result, list) and "retry" in sdp_result):
                    logger.debug("SDP not ready, retrying (%d/10)...", attempt + 1)
                    await asyncio.sleep(1)
                    continue
            except Exception as e:
                logger.debug("SDP fetch attempt %d failed: %s", attempt + 1, e)
                await asyncio.sleep(1)
        else:
            raise RuntimeError("Timeout waiting for device SDP answer")

        dev_sdp_b64 = sdp_result["dev_sdp"]
        dev_sdp_json = json.loads(base64.b64decode(dev_sdp_b64))
        answer = RTCSessionDescription(sdp=dev_sdp_json["sdp"], type=dev_sdp_json["type"])
        await self.session.pc.setRemoteDescription(answer)

        # Step 8: Exchange ICE candidates
        logger.info("Exchanging ICE candidates...")

        # Send our ICE candidates
        candidates = []
        @self.session.pc.on("icecandidate")
        def on_ice(candidate):
            if candidate:
                candidates.append(candidate)

        await asyncio.sleep(2)  # Gather candidates

        for candidate in candidates:
            ice_json = json.dumps({
                "candidate": candidate.candidate,
                "sdpMid": candidate.sdpMid,
                "sdpMLineIndex": candidate.sdpMLineIndex,
            })
            ice_b64 = base64.b64encode(ice_json.encode()).decode()
            try:
                await self.session.rpc.send_command(
                    "send_ice_to_robot", params={"app_ice": ice_b64}
                )
            except Exception as e:
                logger.debug("Error sending ICE: %s", e)

        # Get device ICE candidates
        try:
            ice_result = await self.session.rpc.send_command("get_device_ice")
            if isinstance(ice_result, list) and len(ice_result) > 0:
                ice_result = ice_result[0]
            if isinstance(ice_result, dict) and "dev_ice" in ice_result:
                for ice_b64 in ice_result["dev_ice"]:
                    ice_json = json.loads(base64.b64decode(ice_b64))
                    candidate = RTCIceCandidate(
                        sdpMid=ice_json.get("sdpMid", "0"),
                        sdpMLineIndex=ice_json.get("sdpMLineIndex", 0),
                        candidate=ice_json["candidate"],
                    )
                    await self.session.pc.addIceCandidate(candidate)
        except Exception as e:
            logger.debug("Error getting device ICE: %s", e)

        # Wait for connection
        logger.info("Waiting for WebRTC connection...")
        for _ in range(30):
            if self.session.pc.connectionState == "connected":
                break
            await asyncio.sleep(0.5)
        else:
            state = self.session.pc.connectionState
            raise RuntimeError(f"WebRTC connection failed (state: {state})")

        self.session.running = True
        logger.info("✅ Camera connected!")

    async def snapshot(self, output_path: str = "snapshot.jpg") -> str:
        """Capture a single frame and save as JPEG."""
        if not self.session.video_track:
            raise RuntimeError("No video track available. Is the camera connected?")

        frame = await self.session.video_track.recv()
        img = frame.to_ndarray(format="bgr24")

        # Save with av/PIL
        output = Path(output_path)
        container = av.open(str(output), mode="w")
        stream = container.add_stream("mjpeg", rate=1)
        stream.width = img.shape[1]
        stream.height = img.shape[0]
        stream.pix_fmt = "yuvj420p"

        av_frame = av.VideoFrame.from_ndarray(img, format="bgr24")
        for packet in stream.encode(av_frame):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()

        logger.info("Snapshot saved: %s", output_path)
        return str(output)

    async def record(self, output_path: str = "recording.mp4", duration: int = 30) -> str:
        """Record video for specified duration (seconds)."""
        if not self.session.video_track:
            raise RuntimeError("No video track available.")

        logger.info("Recording %ds to %s...", duration, output_path)
        recorder = MediaRecorder(output_path)
        recorder.addTrack(self.session.video_track)
        if self.session.audio_track:
            recorder.addTrack(self.session.audio_track)

        await recorder.start()
        await asyncio.sleep(duration)
        await recorder.stop()

        logger.info("Recording saved: %s", output_path)
        return output_path

    async def stream_mjpeg(self, host: str = "127.0.0.1", port: int = 8554) -> None:
        """Start an MJPEG HTTP stream server for browser/VLC viewing.

        View at: http://localhost:8554/stream
        """
        from aiohttp import web

        if not self.session.video_track:
            raise RuntimeError("No video track available.")

        async def handle_stream(request):
            response = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "multipart/x-mixed-replace; boundary=frame",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            await response.prepare(request)

            logger.info("Client connected to MJPEG stream: %s", request.remote)
            try:
                while self.session.running:
                    frame = await self.session.video_track.recv()
                    img = frame.to_ndarray(format="bgr24")

                    # Encode frame as JPEG
                    output = av.open(None, mode="w", format="image2pipe")
                    stream = output.add_stream("mjpeg", rate=1)
                    stream.width = img.shape[1]
                    stream.height = img.shape[0]
                    stream.pix_fmt = "yuvj420p"
                    av_frame = av.VideoFrame.from_ndarray(img, format="bgr24")

                    jpeg_data = b""
                    for packet in stream.encode(av_frame):
                        jpeg_data += bytes(packet)
                    for packet in stream.encode():
                        jpeg_data += bytes(packet)
                    output.close()

                    await response.write(
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg_data)).encode() + b"\r\n\r\n"
                        + jpeg_data + b"\r\n"
                    )
            except (ConnectionResetError, asyncio.CancelledError):
                logger.info("Client disconnected from MJPEG stream")
            return response

        async def handle_index(request):
            html = """<!DOCTYPE html>
<html><head><title>Roborock Camera</title></head>
<body style="margin:0;background:#000;display:flex;justify-content:center;align-items:center;height:100vh">
<img src="/stream" style="max-width:100%;max-height:100vh">
</body></html>"""
            return web.Response(text=html, content_type="text/html")

        app = web.Application()
        app.router.add_get("/", handle_index)
        app.router.add_get("/stream", handle_stream)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        print(f"🎥 MJPEG stream available at:")
        print(f"   Browser: http://localhost:{port}/")
        print(f"   VLC:     http://localhost:{port}/stream")
        print(f"   Press Ctrl+C to stop")

        # Keep running
        try:
            while self.session.running:
                await asyncio.sleep(1)
        finally:
            await runner.cleanup()

    async def disconnect(self) -> None:
        """Close camera session and all connections."""
        self.session.running = False

        if self.session.rpc:
            try:
                await self.session.rpc.send_command("stop_camera_preview")
            except Exception:
                pass

        if self.session.pc:
            await self.session.pc.close()

        if self.session.mqtt_session:
            await self.session.mqtt_session.close()

        logger.info("Camera disconnected")


async def camera_snapshot(config: dict, output: str = "snapshot.jpg",
                          password: str = "", quality: str = "HD",
                          device_index: int = 0) -> str:
    """Convenience function: connect, take snapshot, disconnect."""
    camera = RoborockCamera(config, CameraConfig(
        pattern_password=password, quality=quality, device_index=device_index
    ))
    try:
        await camera.connect()
        return await camera.snapshot(output)
    finally:
        await camera.disconnect()


async def camera_record(config: dict, output: str = "recording.mp4",
                        duration: int = 30, password: str = "",
                        quality: str = "HD", device_index: int = 0) -> str:
    """Convenience function: connect, record, disconnect."""
    camera = RoborockCamera(config, CameraConfig(
        pattern_password=password, quality=quality, device_index=device_index
    ))
    try:
        await camera.connect()
        return await camera.record(output, duration)
    finally:
        await camera.disconnect()


async def camera_stream(config: dict, host: str = "127.0.0.1", port: int = 8554,
                        password: str = "", quality: str = "HD",
                        device_index: int = 0) -> None:
    """Convenience function: connect and start MJPEG stream server."""
    camera = RoborockCamera(config, CameraConfig(
        pattern_password=password, quality=quality, device_index=device_index
    ))
    try:
        await camera.connect()
        await camera.stream_mjpeg(host, port)
    finally:
        await camera.disconnect()
