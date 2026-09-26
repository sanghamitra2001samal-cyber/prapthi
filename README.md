# VoxForge

A browser-based, **API-free** text-to-speech studio — modeled on the ElevenLabs
UX but built without any third-party TTS API. Free, private, no signup.

Built to the specs in `VoxForge_PRD_Comprehensive`, `VoxForge_Website_Flow`,
and `VoxForge_TRD`.

> **Positioning (honest):** VoxForge competes on being free, private, and
> instant — not on matching ElevenLabs' proprietary emotive realism. Voice
> quality comes from your OS voices and self-hosted open-source engines, never
> a paid cloud model.

---

## What's here

```
calling/
  web/      React + Vite + TS + Tailwind single-page app (the Studio)
  server/   Starlette + Piper / macOS `say` self-hosted voice service
  *.docx    PRD, Website Flow, TRD
```

### Two voice paths (TRD §4, §7)

| Path | Engine | Network | Download |
|------|--------|---------|----------|
| **Browser voice** | Web Speech API (your OS voices) | None — text never leaves your device | Best-effort tab-audio capture |
| **Downloadable voice** | Self-hosted server (`say` on macOS, Piper elsewhere) | Text → *your own* server, nothing stored | Real WAV (MP3 if `ffmpeg` present) |

No third-party TTS API is used in either path.

---

## Quick start

### Easiest: one command

```bash
./start.sh
```

Installs anything missing (web deps + Python venv), then boots **both** the
backend and the front-end together. Open http://localhost:5173 and press
Ctrl+C to stop both. Use `./start.sh --setup` to only install.

> `start.sh` creates the backend venv with Python 3.12/3.13 if available (the
> Piper neural voice needs it — `onnxruntime` has no 3.14 wheel yet) and falls
> back to `python3` otherwise (macOS `say` still works there).

The manual two-terminal flow is below.

### 1. Front-end (works on its own with browser voices)

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

That alone gives you the full Studio with your browser's voices, playback,
word highlighting, history, and best-effort export.

### 2. Backend (adds guaranteed downloadable audio files)

```bash
cd server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --port 8000
```

On **macOS** this works immediately — it uses the built-in, on-device `say`
command (70+ voices, real WAV files, no model download).

To add the **Piper neural voice** (cross-platform, higher quality than `say`):

```bash
./setup.sh           # downloads an English neural voice model (~63 MB)
pip install piper-tts # needs Python 3.12/3.13 (no 3.14 wheel yet)
uvicorn app:app --port 8000
```

`setup.sh` fetches the most human-sounding open voices across three engines,
all running together (force one with `VOXFORGE_ENGINE=kokoro|piper|say`):

| Engine | Quality | Voices | SR |
|--------|---------|--------|-----|
| **Kokoro** ⭐ | most human ("Ultra") | Heart, Bella, Michael, Emma, George… | 24 kHz |
| **Piper** | very natural ("Neural, High/Medium") | Lessac, Ryan, Jenny, Amy | 22 kHz |
| **macOS `say`** | OS voices (breadth) | Samantha, Daniel, … (70) | 22 kHz |

The picker labels each by tier and lists the best first, so a fresh visit
defaults to a **Kokoro** voice. Drop any extra Piper `.onnx` into
`server/models/` (or Kokoro files into `server/models/kokoro/`) and they appear
automatically.

> **For the most natural sound, pick a "Kokoro, Ultra" voice** (e.g. Heart or
> Michael). All server audio is auto-polished: DC-removed, silences trimmed,
> **loudness-matched to a constant level** (so voices don't jump in volume),
> peak-limited (no clipping), and de-clicked with short edge fades.

**Indian voices.** Filter the picker by language to find them. Neural
(high-quality) coverage:

| Language | Voices (neural) | Engine |
|----------|-----------------|--------|
| Hindi `hi` | Aria, Diya, Arjun, Kabir | Kokoro (Ultra, 24 kHz) |
| Hindi `hi` | Priyamvada (f), Rohan (m) | Piper |
| Telugu `te` | Maya (f), Venkatesh (m) | Piper |
| Malayalam `ml` | Meera (f), Arjun (m) | Piper |

| Tamil `ta` · Bengali `bn` · Kannada `kn` | one neural voice each | MMS (opt-in) |
| Gujarati `gu` · Marathi `mr` · Punjabi `pa` | one neural voice each | MMS (opt-in) |

| **HD — all 9 above** | 2 speakers each, "(Parler, HD)" | Indic Parler-TTS (opt-in) |

Type in the matching script and pick the matching voice. The Tamil…Punjabi row
comes from Meta's **MMS** engine — install it with `cd server && ./setup.sh mms`
(adds PyTorch + ~840 MB of models). macOS also provides standard-quality
**Rishi** (Indian English); no open *neural* Indian-English model exists yet.

**HD tier (most human).** AI4Bharat **Indic Parler-TTS** gives the most
human-sounding Indian voices (44.1 kHz, 18 voices across 9 languages, labelled
"(Parler, HD)"). It's **gated + heavy**: the model is ~3.5 GB and runs CPU-only
here, so each clip takes **~75–95 s**. Install it opt-in:

```bash
# 1) accept the licence at huggingface.co/ai4bharat/indic-parler-tts
# 2) use a CLASSIC "Read" token (fine-grained tokens lack gated-repo access)
export HF_TOKEN=hf_xxx
cd server && ./setup.sh parler
```

> MMS voices are 16 kHz and load lazily — the **first** request per language
> takes a few seconds. Parler is the highest quality but slow on CPU; it's an
> opt-in "HD" choice, never the default, so the fast voices stay instant.

> **MP3:** with `ffmpeg` installed (`brew install ffmpeg`), `/synthesize`
> returns real MP3s; without it, it falls back to WAV.

The Vite dev server proxies `/api` → `http://127.0.0.1:8000`, so once the
backend is running, **"Downloadable" voices appear automatically** in the
voice picker.

### Production build

```bash
cd web && npm run build      # static bundle in web/dist (host on any CDN)
cd ../server && docker build -t voxforge-server .   # containerized backend
```

---

## Accounts & Authentication

The whole app is **gated behind login**. Full account system backed by
**PostgreSQL**: sign up, email verification (6-digit code), login, and password
reset.

### Setup (PostgreSQL)
```bash
brew install postgresql@18 && brew services start postgresql@18
createdb ayaanvoice
# driver is in requirements.txt: pip install -r server/requirements.txt
```
Connection string via `VOXFORGE_DATABASE_URL` (default `postgresql:///ayaanvoice`).
Tables are created automatically on first server start.

### Flows
- **Sign up** → account created (unverified) → 6-digit code emailed → **Verify**
  → welcome email → can sign in.
- **Login** → only verified accounts; sends a "new sign-in" alert email.
- **Forgot / Reset password** → reset code emailed → set new password (revokes
  all existing sessions).
- Endpoints: `POST /auth/signup · /auth/verify · /auth/resend · /auth/login ·
  /auth/logout · /auth/forgot · /auth/reset`, `GET /auth/me`.

### Email delivery
`VOXFORGE_EMAIL_MODE` = `console` (default — codes print to the server log, so
everything works with no mail setup) or `smtp` (set
`VOXFORGE_SMTP_HOST/PORT/USER/PASSWORD/FROM` to send real email via stdlib
`smtplib` — no third-party API).

### Master admin
Auto-created on first run: `admin@ayaanvoice.local` + a random password written
to `server/MASTER_CREDENTIALS.txt` (git-ignored) and printed to the log.
Override with `VOXFORGE_MASTER_USER` / `VOXFORGE_MASTER_PASSWORD`.

### Security
scrypt password hashing (n=2¹⁷, per-record params, never plaintext); httpOnly +
SameSite=Strict session cookie (12h) with **server-side revocation** (logout /
password change invalidate tokens); per-IP rate limiting on login/signup/reset;
codes stored only as SHA-256, single-use, 15-min expiry, attempt-capped; no
account enumeration. Set `VOXFORGE_SECURE_COOKIE=1` in production (HTTPS).

## API contract (TRD §5.2)

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/health` | liveness probe |
| `GET`  | `/voices` | list self-hosted voices |
| `POST` | `/synthesize` | `{text, voiceId, rate, pitch, volume, format}` → audio bytes |
| `POST` | `/preview` | short sample for a voice |

`/synthesize` returns `audio/wav` (always) or `audio/mpeg` (if `ffmpeg` is
installed). Errors: `400` invalid · `413` too long · `429` rate-limited ·
`500` synthesis failure. No user text is logged or persisted.

### Configuration (env vars)

| Var | Default | Meaning |
|-----|---------|---------|
| `VOXFORGE_ENGINE` | auto | `say` or `piper` to force an engine |
| `VOXFORGE_CHAR_CAP` | `5000` | per-request character cap |
| `VOXFORGE_RATE_LIMIT` | `60` | requests/min per IP |
| `VOXFORGE_ALLOWED_ORIGIN` | `*` | CORS origin allow-list |
| `VITE_API_BASE` | `/api` | front-end → backend base URL |

---

## Features (per PRD §6 / Website Flow)

- **S1 Studio** — editor with live word/char count, paste sanitizing, 5,000-char
  cap, Play/Pause/Resume/Stop, progress bar, word highlighting (background +
  underline, not color alone).
- **S2 Voice Picker** — search, language/gender/downloadable filters, per-voice
  preview, select.
- **S3 History** — last 20 generations in `localStorage`, replay / re-export /
  delete (with undo) / clear. No server storage.
- **S4 Export** — WAV/MP3 for server voices; best-effort tab capture for browser
  voices, with a clear "switch voice" recovery.
- **S5 Settings** — rate / pitch / volume sliders, clamping, reset to defaults.
- **S6 Help**, **S7 About/Privacy**, **S8 404**.
- **Global** — keyboard shortcuts (Space, Esc, ⌘/Ctrl+Enter, ⌘/Ctrl+S), toasts,
  responsive layout, WCAG 2.1 AA focus management and focus-trapped overlays.

## Privacy

- Browser-voice path makes **zero network calls with your text**.
- No accounts, no analytics on text content, no server-side storage of user text.
- History lives only in your browser's local storage.

## Out of scope for v1 (PRD §14)

Voice cloning, accounts/billing, large premium voice libraries, emotion/style
controls, long-form synthesis, collaboration, public third-party API, native
apps.
