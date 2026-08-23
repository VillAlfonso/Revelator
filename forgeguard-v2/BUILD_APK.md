# Building the Revelator Android APK

## Prerequisites

1. **Android Studio** - [download here](https://developer.android.com/studio)
   - Installs JDK 17 and Android SDK automatically
   - After install, set `ANDROID_HOME` env var to your SDK path (e.g. `C:\Users\YOU\AppData\Local\Android\Sdk`)
2. **Node.js** v18+ - [nodejs.org](https://nodejs.org)
3. Phone and laptop on the **same WiFi network**

---

## Build Steps

Run these from `C:\Revelator\frontend`:

```powershell
npm run build
npx cap sync android
cd android
.\gradlew.bat assembleDebug
```

APK output: `android\app\build\outputs\apk\debug\app-debug.apk`

---

## Install on Your Phone

1. Copy the APK to your phone (USB cable, Google Drive, or email)
2. On your phone: **Settings → Security → Install unknown apps** → enable for Files or Chrome
3. Open the APK file on your phone and tap **Install**

---

## Before Launching the App

The app connects to your local backend over WiFi. Make sure:

1. **Backend is running** on your PC: `python run.py`
   - It must bind to `0.0.0.0` (not just localhost) - this is already configured
2. **Windows Firewall** - when prompted, click **Allow** for port 8000
3. **Verify connectivity** - open `http://192.168.0.169:8000/docs` in your phone's browser. If it loads, you're good.

> If your PC's LAN IP changes, update `frontend\.env` → `VITE_API_URL=http://NEW_IP:8000` and rebuild.

---

## Alternative: Run Directly from Android Studio

```powershell
npx cap open android
```

Connect your phone via USB (with USB debugging enabled in Developer Options), then press the green **Run** button in Android Studio. Builds and installs in one step - easier for active development.

---

## Signing for Play Store (Release Build)

```powershell
keytool -genkey -v -keystore revelator.keystore -alias revelator -keyalg RSA -keysize 2048 -validity 10000
```

Configure signing in `android\app\build.gradle`, then:

```powershell
.\gradlew.bat assembleRelease
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `SDK not found` | Create `android\local.properties` with `sdk.dir=C:\\Users\\YOU\\AppData\\Local\\Android\\Sdk` |
| API calls failing | Confirm phone and PC are on same WiFi; check `VITE_API_URL` in `frontend\.env` |
| Camera not working | Run `npx cap sync android` after any plugin changes |
| `gradlew.bat` not found | Make sure you're inside `frontend\android`, not `frontend` |
| App installs but white screen | Check browser console via `chrome://inspect` - usually a CORS or wrong IP issue |
