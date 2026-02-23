# ADB Credential Extraction (Android)

Use this only if `roborock-cli setup` fails (captcha loops, email-code delivery issues, or repeated auth errors).

This method uses Android `adb logcat` to capture the app login payload, then uses the captured token to query device data (including `local_key`) from Roborock Cloud.

If you already have a log capture or extracted payload, this project now includes a built-in command:

```bash
roborock-cli adb-setup --log-file roborock_log.txt --email you@example.com
```

Or:

```bash
roborock-cli adb-setup --extracted-json roborock_extracted.json --email you@example.com
```

## Security First

- Treat extracted values as secrets: `token`, `rriot.*`, `local_key`.
- Do not commit logs or extracted JSON files.
- Redact all secrets before sharing logs in issues.

## Prerequisites

- Android phone with Roborock app installed and logged in.
- USB debugging enabled.
- `adb` installed and available in PATH.

## 1. Verify ADB connection

```bash
adb devices
```

Expected: your device appears as `device` (not `unauthorized`).

## 2. Capture focused Roborock logs

Broad filters like `token` can pull unrelated app logs. Prefer PID-filtered capture.

1. Force-stop app and clear old logs:

```bash
adb shell am force-stop com.roborock.smart
adb logcat -c
```

2. Launch app:

```bash
adb shell monkey -p com.roborock.smart -c android.intent.category.LAUNCHER 1
```

3. Get app PID:

```bash
adb shell pidof -s com.roborock.smart
```

4. Start capture:

Linux/macOS:
```bash
PID=$(adb shell pidof -s com.roborock.smart | tr -d '\r')
adb logcat --pid "$PID" -v time | tee roborock_log.txt
```

PowerShell:
```powershell
$pid = (adb shell pidof -s com.roborock.smart).Trim()
adb logcat --pid $pid -v time | Tee-Object -FilePath roborock_log.txt
```

Then open the Roborock app and navigate account/home screen until you see a line with:

- `FeatureCacheService->loadLoginResponse`

This line contains escaped JSON with `token`, `uid`, `rruid`, and `rriot`.

## 3. Extract login payload

The easiest reliable trigger from real captures is:

- `ReactNativeJS: 'FeatureCacheService->loadLoginResponse', '"{...}"'`

You can isolate this line first:

```bash
grep -i "FeatureCacheService->loadLoginResponse" roborock_log.txt
```

PowerShell:
```powershell
Select-String -Path roborock_log.txt -Pattern "FeatureCacheService->loadLoginResponse"
```

## 4. Decode escaped JSON to `roborock_extracted.json`

```python
import json
from pathlib import Path

line = None
for raw_line in Path("roborock_log.txt").read_text(encoding="utf-8", errors="ignore").splitlines():
    if "FeatureCacheService->loadLoginResponse" in raw_line:
        line = raw_line
        break

if not line:
    raise SystemExit("No FeatureCacheService->loadLoginResponse line found")

start = line.find('"{\\')
end = line.rfind('}"')
if start == -1 or end == -1:
    raise SystemExit("Could not locate escaped JSON payload in line")

escaped_json = line[start + 1 : end + 1]
decoded_json = bytes(escaped_json, "utf-8").decode("unicode_escape")
payload = json.loads(decoded_json)

out = {
    "token": payload.get("token"),
    "uid": payload.get("uid"),
    "rruid": payload.get("rruid"),
    "region": payload.get("region"),
    "country": payload.get("country"),
    "nickname": payload.get("nickname"),
    "rriot": payload.get("rriot"),
}

Path("roborock_extracted.json").write_text(
    json.dumps(out, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
print("Wrote roborock_extracted.json")
```

## 5. Get device data (`duid`, `local_key`) from cloud API

From the extracted JSON:

- `token` -> Authorization header
- `rriot.r.a` -> API base URL (for example `https://api-eu.roborock.com`)

Request home details:

```bash
curl -H "Authorization: YOUR_TOKEN" \
  "https://api-eu.roborock.com/api/v1/getHomeDetail"
```

From the response, copy per-device:

- `duid`
- `local_key`
- `name`
- `product_id`

## 6. Build `config.json`

Create config path:

```bash
mkdir -p ~/.config/roborock-cli
cp config.example.json ~/.config/roborock-cli/config.json
chmod 600 ~/.config/roborock-cli/config.json
```

Fill:

- `email`
- `rriot` from `roborock_extracted.json`
- `devices[]` entries from `getHomeDetail` response

Validate:

```bash
roborock-cli devices
roborock-cli status
```

Equivalent one-step CLI command:

```bash
roborock-cli adb-setup --log-file roborock_log.txt --email you@example.com
```

## Troubleshooting

- No `FeatureCacheService->loadLoginResponse` line:
  - Re-login inside app.
  - Force-stop app, clear logs, and capture again.
  - Ensure you are filtering with Roborock PID.
- `401`/auth errors on `getHomeDetail`:
  - Token expired; repeat capture.
  - Confirm API base URL from `rriot.r.a`.
- Wrong region:
  - Use the region in captured `rriot.r.r` and endpoint in `rriot.r.a`.

## Notes

- This approach was validated from real captures where the login payload was visible in `ReactNativeJS` logs.
- `.ab` backups are not required for this flow.
