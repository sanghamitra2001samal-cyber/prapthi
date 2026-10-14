# Prapthi AI — Android & iOS app

A native shell (Capacitor 8) around the live studio at `https://prapthi.ai/app/`.

**Why it loads the live site instead of bundling the studio.** The login cookie
is `httpOnly` + `SameSite=Strict` and the API only allows credentialed requests
from its own origin. A bundled app would run at `https://localhost` /
`capacitor://localhost`, be cross-site to prapthi.ai, and every signed-in call
would fail. Loading prapthi.ai keeps the app first-party: login, Razorpay,
caching and every studio work exactly as on the website, with no backend
changes — and every web deploy reaches the app immediately, without a store
update. Bump `?v=` on web deploys as usual (see the cache-busting note).

## What the native shell adds

A WebView alone is not a browser. These are the gaps it fills:

| Gap in a plain WebView | Fix | Where |
|---|---|---|
| Download buttons do nothing | Every `<a download>` (blob or URL) and attachment response is saved through the phone's share/save sheet, chunked so long WAVs never cross the bridge as one string | `www/native-shell.js`, `ShellPlugin.java` |
| Razorpay bank / 3-D Secure pop-ups replace the app or escape to the browser | Real pop-up windows that keep `window.opener`, close on `window.close()`, and have a Close button | `ShellChromeClient.java`, `ShellUIDelegate.swift` |
| UPI app links (`upi://`, `intent://`, `tez://`…) are swallowed | Handed to the UPI app; `intent://` falls back to its web address or Play listing; a toast if no app can open it | `ExternalLinks.java`, `PrapthiShellPlugin.swift` |
| Microphone | Permission declared and asked only when a page records | `AndroidManifest.xml`, `Info.plist` |
| Offline launch shows a cached studio that wrongly looks signed out | Offline screen at launch; reconnects by itself | `MainActivity.java`, `PrapthiViewController.swift`, `www/offline.html` |
| Back button on the first page does nothing (Capacitor default) | Back walks history, then leaves the app | `MainActivity.java` |
| iOS: the site's `/login` is "outside the app" (Capacitor only trusts `/app/`) | The whole prapthi.ai host stays in the app | `PrapthiShellPlugin.swift` |
| iOS: Capacitor runs plugin calls from any page sharing its config, pop-ups included | Only the app's own main frame on prapthi.ai reaches native code | `BridgeMessageFilter` in `PrapthiViewController.swift` |
| Login lost if the app is killed right after signing in; backup copies the cookie to other phones | Cookie store flushed on pause; backup and device transfer excluded | `ShellPlugin.java`, `data_extraction_rules.xml` |

## Layout

```
capacitor.config.json   app id ai.prapthi.app, server URL, offline page
www/                    offline.html, native-shell.js (shared by both platforms)
android/                Android Studio project
ios/App/                Xcode project (Swift Package Manager, no CocoaPods)
scripts/                create-upload-key.sh
store/                  icons for the store listings
```

Edit `www/` and `capacitor.config.json` here, then `npx cap sync` copies them
into both native projects.

## Android

Tools (already installed on this Mac): JDK 21 at `/usr/local/opt/openjdk@21`,
Android SDK at `/usr/local/share/android-commandlinetools`.

```bash
export JAVA_HOME=/usr/local/opt/openjdk@21 ANDROID_HOME=/usr/local/share/android-commandlinetools
npm install
npm run android:debug      # -> android/app/build/outputs/apk/debug/app-debug.apk
```

### Releasing to Google Play
1. Once: `scripts/create-upload-key.sh` — you choose the password; back up
   `android/prapthi-upload.jks` and the password. Both are git-ignored.
2. Raise `versionCode` in `android/app/build.gradle` for every upload.
3. `npm run android:release` → `android/app/build/outputs/bundle/release/app-release.aab`.
4. Play Console: new app, enrol in Play App Signing, upload the `.aab`.
   Listing icon: `store/play-icon-512.png`.
5. Payments: the app sells plans through Razorpay. Google Play requires Play
   Billing for digital goods unless the app is enrolled in its India
   alternative/user-choice billing programme — enrol before submitting.

## iOS

Needs Xcode (Mac App Store) and, to publish, an Apple Developer account.

```bash
npx cap sync ios
open ios/App/App.xcodeproj
```
In Xcode: select the **App** target → Signing & Capabilities → choose your
team. Run on a simulator or device. App Store icon: `store/app-store-icon-1024.png`.

**App Store warning:** Apple guideline 3.1.1 requires In-App Purchase for
digital goods such as character plans. An iOS build that sells plans through
Razorpay will be rejected at review. It works for TestFlight and internal use.

## Checks to do on a real phone, signed in

These need your account, so they were not run during development:
- Sign in, close the app fully, reopen: still signed in.
- Buy a plan from the site's pricing page: Razorpay opens, UPI hands off to
  the UPI app and returns, the plan activates.
- Voice cloning: the mic permission prompt appears and recording works.
- Generate speech and tap Download: the save/share sheet shows the file.
