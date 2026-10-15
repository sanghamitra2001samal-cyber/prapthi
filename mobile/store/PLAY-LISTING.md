# Google Play listing — Prapthi AI

Everything Play Console asks for, ready to paste. Upload file:
`mobile/android/app/build/outputs/bundle/release/app-release.aab` (rebuild with
`npm run android:release` after raising `versionCode`).

## Store listing

**App name** (30 max)
```
Prapthi AI: Text to Speech
```

**Short description** (80 max)
```
Natural AI voices in Indian languages. Text to speech, voice cloning, dubbing.
```

**Full description**
```
Prapthi AI turns your words into natural, expressive speech — in Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Indian English and many more languages.

Write a script, pick a voice and an emotion, and hear it in seconds. Download the audio and use it in videos, reels, podcasts, ads, audiobooks and lessons.

WHAT YOU CAN DO
• Text to Speech — 200+ voices across 50+ languages, with emotions and Hinglish-style mixed text
• Voice Cloning — create a voice from a short recording of your own
• AI Dubbing — dub a video into another language
• Speech to Text — turn recordings into text
• Audiobook Studio — narrate long scripts chapter by chapter
• Create Song and Sargam Studio — AI songs and Indian melodies
• Sound Effects, Voice Isolator, Voice Agent and an Ads Engine

BUILT FOR INDIA
Voices made for Indian languages and accents, including text that mixes English with Hindi or Bengali.

PLANS
Start free with a monthly character allowance. Paid plans add more characters, every premium voice, voice cloning, WAV downloads and commercial rights. Plans run for 30 days and never renew automatically.

Your account works on the web too: sign in at prapthi.ai with the same email.

Privacy policy: https://prapthi.ai/privacy
Delete your account: https://prapthi.ai/delete-account
```

**Graphics** (all in `mobile/store/`)
| Asset | File |
|---|---|
| App icon 512×512 | `play-icon-512.png` |
| Feature graphic 1024×500 | `play-feature-graphic-1024x500.png` |
| Phone screenshots (5, 1080×1920) | `play-screenshots/01-home.png` … `05-login.png` |

The screenshots show the public pages, because they were taken without an
account. For a stronger listing, replace two or three with the studio itself
(Text to Speech, Voice Cloning) taken on your own phone while signed in.

**Category:** Productivity (alternative: Music & Audio)
**Contact email:** info@prapthi.ai · **Website:** https://prapthi.ai

## App content (Policy → App content)

**Privacy policy URL:** `https://prapthi.ai/privacy`

**Account deletion**
- In-app: account menu → *Delete account* (password required; immediate).
- Web link for the form: `https://prapthi.ai/delete-account`
- Data deleted: account, email, password, cloned voices and recordings, songs
  and audio files, remaining allowance.
- Data kept: payment records (amount, plan, date, email), for legal/tax reasons.

**Data safety** — answer as follows:
- Does the app collect or share user data? **Yes, collects. Does not share.**
- Encrypted in transit? **Yes** (HTTPS only).
- Can users request deletion? **Yes.**

| Data type | Collected | Optional? | Ephemeral? | Purposes |
|---|---|---|---|---|
| Personal info → Email address | Yes | Required | No | Account management, App functionality, Security (sign-in alerts) |
| Financial info → Purchase history | Yes | Optional (only if a plan is bought) | No | Account management, App functionality |
| Audio → Voice or sound recordings | Yes | Optional | No (voice clones are kept until deleted) | App functionality |
| Files and docs | Yes | Optional (dubbing / isolator uploads) | Yes | App functionality |
| App activity → Other user-generated content (text turned into speech) | Yes | Required to use the app | Yes | App functionality |

Not collected: location, contacts, photos, device or advertising IDs,
analytics, crash logs (none of these are gathered by the app or the site).
Card and UPI details are entered on Razorpay's checkout and never reach
Prapthi's servers, so *Financial info → Payment info* is not declared.

**Ads:** No ads. **Target audience:** 18 and over.
**Content rating questionnaire:** Utility/productivity app; no violence, sexual
content, gambling or drugs. Users can generate audio from their own text
(answer *yes* to "user-generated content" if asked, with the Terms as moderation
policy: https://prapthi.ai/terms).

**Payments (important before submitting):** plans are sold through Razorpay.
Google Play requires Play Billing for digital goods unless the app is enrolled
in Play's alternative / user-choice billing programme for India. Enrol in
Play Console → Monetisation setup before sending the app for review.

## Signing

- Upload key: `mobile/android/prapthi-upload.jks`, password in
  `mobile/android/keystore.properties` (both git-ignored, readable only by you).
- **Back both up now** (password manager + an offline copy). With Play App
  Signing a lost upload key can be reset, but it takes days.
- Upload certificate SHA-256:
  `c6:0f:ce:a0:67:45:57:97:ed:5c:be:a7:f3:1c:5a:af:79:87:70:88:4d:bb:45:ea:7d:97:c8:9e:fd:53:34:c5`
- When creating the app, choose **Play App Signing** (Google holds the app
  signing key; this file is only the upload key).

## Release checklist

1. Play Console → Create app → name, default language English (India), App, Free.
2. Fill *App content* above (privacy, deletion, data safety, rating, audience, ads).
3. Enrol in alternative billing for India.
4. Store listing: paste text, upload graphics.
5. Testing → Internal testing → upload the `.aab`, add your own email as a
   tester, install from the opt-in link, and check sign-in, generate,
   download, buy a plan, record a clone, delete a test account.
6. Production → promote the tested release.
