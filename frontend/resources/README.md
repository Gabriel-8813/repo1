# MediTrans App Store Assets

## Source assets (this folder)
- `icon.png` — 1024×1024 master app icon (clinical blue #0369a1, medical delivery van)
- `splash.png` — 2732×2732 master splash (white, centered MediTrans emblem + "Ontario's Medical Transport Network")
- `store-screenshots/` — 4 framed marketing screenshots at 1290×2796 (iPhone 6.7" App Store size):
  1. `store_1_login.png` — Welcome / sign-in
  2. `store_2_jobs.png` — Job Board with live medical transport jobs
  3. `store_3_earnings.png` — Driver earnings & trip history
  4. `store_4_dashboard.png` — Driver dashboard overview

## Native assets (already generated)
`npx @capacitor/assets generate --ios --android` has been run:
- iOS: `ios/App/App/Assets.xcassets/` (AppIcon + Splash, 10 files)
- Android: `android/app/src/main/res/` (adaptive icons + splash drawables, 87 files)

Re-run the command above after changing `icon.png` / `splash.png`.

## Reviewer demo accounts
See `/app/memory/test_credentials.md` — demo.driver / demo.facility / demo.dispatcher / demo.admin @meditrans.ca.
