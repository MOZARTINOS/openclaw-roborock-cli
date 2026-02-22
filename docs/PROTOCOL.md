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

## Security Notes

- All MQTT traffic is encrypted via TLS
- Message payloads are encrypted with device-specific `local_key` (AES-128-ECB)
- Authentication uses HMAC-derived credentials, not raw passwords
- The `rriot` secret values should be treated as sensitive credentials

## Credits

Protocol implementation based on [python-roborock](https://github.com/Python-roborock/python-roborock).
