# ADB Token Extraction Guide

If the standard `roborock-cli setup` flow doesn't work (e.g., 2FA issues, rate limiting), you can extract credentials directly from the Roborock app on your Android phone.

## Prerequisites

- Android phone with the **Roborock** app installed and logged in
- **USB Debugging** enabled on the phone
- **ADB** installed on your computer ([download](https://developer.android.com/tools/adb))

## Steps

### 1. Enable USB Debugging

Go to **Settings → About phone → tap "Build number" 7 times** to enable Developer Options.

Then go to **Settings → Developer options → Enable USB Debugging**.

### 2. Connect phone via USB

```bash
adb devices
# Should show your device
```

### 3. Capture login data from logs

The Roborock app logs connection details. Clear logcat and open the app:

```bash
# Clear old logs
adb logcat -c

# Start capturing (open Roborock app on your phone now)
adb logcat | grep -iE "mqtt|rriot|token|uid|duid|local_key"
```

### 4. Look for these values

You need to find:

| Field | Example | Where to find |
|-------|---------|---------------|
| `token` | `rrXXXXXXXXXXXXXX:abcdef123456...` | Login response |
| `uid` | `1234567` | Login response |
| `rruid` | `rrXXXXXXXXXXXXXX` | Login response |
| `mqtt url` | `ssl://mqtt-eu-2.roborock.com:8883` | Connection setup |
| `duid` | `your_device_duid_here` | Device data |
| `local_key` | `your_local_key_here` | Device data |

### 5. Use the token to get full credentials

Once you have the token, you can use it to call the API and get the `rriot` data needed for MQTT:

```bash
# Request verification code
curl -X POST "https://euiot.roborock.com/api/v1/sendEmailCode?username=YOUR_EMAIL&type=auth"

# Login with code (check your email)
curl -X POST "https://euiot.roborock.com/api/v1/loginWithCode?username=YOUR_EMAIL&verifycode=CODE&verifycodetype=AUTH_EMAIL_CODE"
```

The login response contains the `rriot` object with `u`, `s`, `h`, `k` values needed for MQTT authentication.

### 6. Create config manually

Copy `config.example.json` to `~/.config/roborock-cli/config.json` and fill in the values:

```bash
mkdir -p ~/.config/roborock-cli
cp config.example.json ~/.config/roborock-cli/config.json
chmod 600 ~/.config/roborock-cli/config.json
# Edit with your values
```

## Tips

- **Region matters**: EU accounts use `euiot.roborock.com`, US uses `usiot.roborock.com`
- **Token expiration**: Tokens may expire. Re-run `roborock-cli setup` to refresh.
- **Rate limiting**: If you get error 2018, wait a few minutes before trying again.
- **2FA bypass**: The email code login method works even with 2FA enabled on the account.

## iOS

Unfortunately, iOS does not provide easy log access like Android's `adb logcat`. 
Use the `roborock-cli setup` command instead (email + verification code).
