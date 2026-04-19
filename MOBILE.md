# MediTrans — Mobile App (iOS + Android) Build Guide

The MediTrans app is wrapped with **Capacitor 7** so the same React codebase
runs as a native iOS + Android app. This document walks you through taking the
generated projects to the App Store and Google Play.

---

## 📱 App Identity
| Field       | Value              |
|-------------|--------------------|
| App Name    | `MediTrans`        |
| Bundle ID   | `ca.meditrans.app` |
| Config file | `frontend/capacitor.config.json` |

Changing the Bundle ID later requires re-registering with Apple/Google, so
confirm it's correct **before** your first App Store submission.

---

## 🔧 Prerequisites (Your Machine)

| Target   | Need                                                                 |
|----------|----------------------------------------------------------------------|
| iOS      | macOS 13+, Xcode 15+, CocoaPods (`sudo gem install cocoapods`), Apple Developer Program membership (\$99/yr) |
| Android  | Android Studio (latest), JDK 17+, Google Play Console (\$25 one-time) |

Node 20+ and yarn are required to rebuild the web assets.

---

## 🚀 First-Time Setup (on your Mac)

```bash
# 1. Clone the repo to your Mac
git clone <your-repo> meditrans
cd meditrans/frontend

# 2. Install JS dependencies
yarn install

# 3. Build the React app + copy into native projects
yarn build:mobile      # alias for: yarn build && npx cap sync

# 4. Install iOS CocoaPods deps (one-time)
cd ios/App && pod install && cd ../..
```

You'll now have two ready-to-open native projects:

```
frontend/
├── ios/App/App.xcworkspace   ← open this in Xcode
└── android/                  ← open this folder in Android Studio
```

---

## 🍎 iOS Build & Submission

```bash
yarn ios:open     # opens Xcode
```

In Xcode:

1. Select the `App` target (top of the left navigator).
2. **Signing & Capabilities** tab → pick your **Team** (your Apple Developer
   account). Xcode will auto-generate a Provisioning Profile.
3. Choose an iOS Simulator or a connected device from the scheme dropdown.
4. ▶️ **Run** — app should launch and hit the backend at
   `REACT_APP_BACKEND_URL` (configured in `frontend/.env`).
5. For App Store submission: **Product → Archive → Distribute App →
   App Store Connect → Upload**. Then submit for review from
   [App Store Connect](https://appstoreconnect.apple.com).

### App Store Review Tips
- **Stripe is allowed** for physical services (medical transport). Apple IAP is
  NOT required here — it's only required for digital goods/subscriptions.
- Include test credentials in the review notes:
  - Driver: `driver1@test.com` / `Driver@123`
  - Admin:  `gabrielosmanhamza@yahoo.com` / `Admin@123`
- Add a privacy policy URL (required by Apple for any app with user accounts).

---

## 🤖 Android Build & Submission

```bash
yarn android:open    # opens Android Studio
```

In Android Studio:

1. Let Gradle sync complete (first time takes a few minutes).
2. ▶️ **Run** on an emulator or connected device.
3. For Google Play submission:
   **Build → Generate Signed Bundle / APK → Android App Bundle**,
   create or use an existing upload key, then upload the `.aab` to
   [Google Play Console](https://play.google.com/console).

---

## 🔁 Rebuilding After Code Changes

Whenever you change React code (anything under `frontend/src`):

```bash
cd frontend
yarn build:mobile
```

Then rebuild in Xcode / Android Studio. That's the full loop.

> Tip: for faster iOS dev, Capacitor supports "live reload" pointing the app at
> your running React dev server. See
> https://capacitorjs.com/docs/guides/live-reload.

---

## 🌐 Backend URL Strategy

The mobile app hits the backend whose URL is baked into the React build from
`REACT_APP_BACKEND_URL` (set in `frontend/.env`).

For production you want a **stable** URL (not the preview URL which can rotate).
Your options, in order of simplicity:

1. **Emergent native deployment** → `https://<your-app>.emergent.host`. Click
   "Deploy" in your Emergent dashboard, then update
   `frontend/.env` → `REACT_APP_BACKEND_URL=https://<your-app>.emergent.host`
   and run `yarn build:mobile` again.
2. Deploy to Render / Heroku / AWS / Fly.io — update
   `REACT_APP_BACKEND_URL` and rebuild.

---

## 🎨 App Icons & Splash Screen

Capacitor scaffolds placeholder icons. To customize:

```bash
cd frontend
yarn add -D @capacitor/assets
# Put a 1024x1024 icon.png and 2732x2732 splash.png in frontend/resources/
npx capacitor-assets generate
npx cap sync
```

See https://capacitorjs.com/docs/guides/splash-screens-and-icons.

---

## 🔐 Permissions

Currently the app requests only network access (none extra in Info.plist).
When you add native features later, edit:

- **iOS**: `frontend/ios/App/App/Info.plist`
- **Android**: `frontend/android/app/src/main/AndroidManifest.xml`

Common permissions to add later:
- Camera (for driver uploading permit photos)
- Location (for real-time driver GPS)
- Push notifications (requires `@capacitor/push-notifications` plugin + APNs
  setup in Apple Developer portal)

---

## ✅ Pre-Submission Checklist

- [ ] Updated `REACT_APP_BACKEND_URL` to production domain
- [ ] Ran `yarn build:mobile` after the URL change
- [ ] Custom app icons + splash screen generated
- [ ] Privacy policy URL live and linked in app (required by both stores)
- [ ] Tested Stripe Connect onboarding flow inside the native webview
- [ ] Added screenshots (6.7" iPhone, 12.9" iPad for iOS; multiple Android sizes)
- [ ] Review notes include test credentials
- [ ] Version number bumped in both Xcode (General → Version/Build) and
      `android/app/build.gradle` (`versionCode`/`versionName`)

Good luck with your first submission! 🚀
