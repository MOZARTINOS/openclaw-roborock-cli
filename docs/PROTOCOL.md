# Roborock MQTT Protocol

Technical documentation of the Roborock cloud MQTT protocol used by this CLI.

## Architecture

```
┌─────────────┐     MQTT (TLS)      ┌──────────────┐
│  CLI Client │◄────────────────────►│  Roborock    │
│  (Python)   │  Port 8883          │  Cloud MQTT  │
└─────────────┘                     └──────────────┘
                                           │
                                    ┌──────┴──────┐
                                    │  Your Robot │
                                    │  (Vacuum)   │
                                    └─────────────┘
```

## MQTT Connection

### Broker

The MQTT broker URL is region-specific:
- **EU**: `ssl://mqtt-eu-2.roborock.com:8883`
- **US**: `ssl://mqtt-us-2.roborock.com:8883`
- **CN**: `ssl://mqtt-cn-2.roborock.com:8883`

### Authentication

MQTT credentials are derived from the `rriot` data obtained during login:

```python
from hashlib import md5

mqtt_username = md5(f"{rriot_u}:{rriot_k}".encode()).hexdigest()[2:10]
mqtt_password = md5(f"{rriot_s}:{rriot_k}".encode()).hexdigest()[16:]
```

### Topics

```
Publish (commands):   rr/m/i/{rriot_u}/{mqtt_username}/{device_duid}
Subscribe (responses): rr/m/o/{rriot_u}/{mqtt_username}/{device_duid}
```

## Message Format

Messages are encrypted with the device's `local_key` using AES-128-ECB.

### Request (sent via dps.101)

```json
{
  "dps": {
    "101": "{\"id\":12345,\"method\":\"get_status\",\"params\":[]}"
  },
  "t": 1708627200
}
```

### Response (received via dps.102)

```json
{
  "dps": {
    "102": "{\"id\":12345,\"result\":[{\"state\":8,\"battery\":100}]}"
  }
}
```

## Available Commands

### Device Control

| Command | Params | Description |
|---------|--------|-------------|
| `app_start` | `[]` | Start full cleaning |
| `app_stop` | `[]` | Stop cleaning |
| `app_pause` | `[]` | Pause cleaning |
| `app_charge` | `[]` | Return to dock |
| `find_me` | `[]` | Make robot beep |
| `set_custom_mode` | `[101-104]` | Set fan speed |

### Room Cleaning

| Command | Params | Description |
|---------|--------|-------------|
| `app_segment_clean` | `[16, 17]` | Clean specific room segments |
| `app_segment_clean` | `[{"segments": [16], "repeat": 2}]` | Multi-pass room cleaning |
| `get_room_mapping` | `[]` | Get segment_id → cloud_room_id map |
| `get_multi_maps_list` | `[]` | List saved maps |

### Status & Info

| Command | Description |
|---------|-------------|
| `get_status` | Battery, state, clean time/area |
| `get_consumable` | Filter, brush, sensor hours |
| `get_clean_summary` | Cleaning history |
| `get_network_info` | WiFi info, IP address |

### Fan Speed Values

| Value | Mode |
|-------|------|
| 101 | Quiet |
| 102 | Balanced |
| 103 | Turbo |
| 104 | Max |
| 105 | Off (Mop only) |

### State Codes

| Code | State |
|------|-------|
| 2-3 | Idle |
| 5 | Cleaning |
| 6 | Returning to dock |
| 8 | Charging |
| 10 | Paused |
| 17 | Zoned cleaning |
| 18 | Segment cleaning |

## Room Discovery

Room-specific cleaning requires mapping between three data sources:

### 1. Cloud Room Names (via REST API)

The Roborock cloud stores room names set in the app. Fetch via Hawk-authenticated API:

```
GET https://api-eu.roborock.com/user/homes/{home_id}
Authorization: Hawk id="{u}",s="{s}",ts="{ts}",nonce="{nonce}",mac="{mac}"
```

Response includes:
```json
{
  "rooms": [
    {"id": 40680870, "name": "Kitchen"},
    {"id": 40680878, "name": "Kids Room"}
  ]
}
```

### 2. Device Room Mapping (via MQTT)

The device maps segment IDs to cloud room IDs:

```json
// get_room_mapping response
[
  [16, "40680870", 14],   // segment 16 → cloud room 40680870
  [17, "40680878", 12],   // segment 17 → cloud room 40680878
]
```

### 3. Final Mapping

Combine both: `segment_id → cloud_id → room_name`

```
Segment 16 → Cloud 40680870 → "Kitchen"
Segment 17 → Cloud 40680878 → "Kids Room"
```

Then use `app_segment_clean` with segment IDs to clean specific rooms.

### Hawk Authentication

Cloud API endpoints that return home/device data use Hawk authentication:

```python
import base64, hashlib, hmac, math, secrets, time

timestamp = math.floor(time.time())
nonce = secrets.token_urlsafe(6)
prestr = ":".join([
    rriot_u, rriot_s, nonce, str(timestamp),
    hashlib.md5(url_path.encode()).hexdigest(),
    "",  # params
    "",  # formdata
])
mac = base64.b64encode(
    hmac.new(rriot_h.encode(), prestr.encode(), hashlib.sha256).digest()
).decode()
header = f'Hawk id="{rriot_u}",s="{rriot_s}",ts="{timestamp}",nonce="{nonce}",mac="{mac}"'
```

## Security Notes

- All MQTT traffic is encrypted via TLS
- Message payloads are encrypted with device-specific `local_key` (AES-128-ECB)
- Authentication uses HMAC-derived credentials, not raw passwords
- The `rriot` secret values should be treated as sensitive credentials

## Credits

Protocol implementation based on [python-roborock](https://github.com/Python-roborock/python-roborock).
