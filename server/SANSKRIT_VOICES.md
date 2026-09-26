# Sanskrit voices

Prapthi Ai ships two Sanskrit options. Both need the GPU box (they are torch
models); neither runs on the macOS `say` dev setup.

| Voice id | Style | Engine | Port |
|---|---|---|---|
| `parler-sa-aryan` | Clear speech | Parler HD (main engine) | in-process |
| `if5-sanskrit` | Clear speech, near-human | IndicF5 microservice | 8004 |
| `vagdhenu-sa-chant` | **Chant / pārāyaṇa** (melodic recitation) | Vāgdhenu microservice | 8006 |

`parler-sa-aryan` works out of the box wherever the Parler model is installed —
"Aryan" is the sole official AI4Bharat speaker for Sanskrit and its highest-
consistency language. The two below are opt-in.

Tip: input **Devanagari** for all Sanskrit voices. Romanized input is *not* run
through the Hindi→Devanagari converter for Sanskrit voices (it is Hindi-specific
and would mangle Sanskrit), so romanized text is spoken as-is.

---

## 1. `if5-sanskrit` — clear Sanskrit speech (IndicF5)

IndicF5 is zero-shot: it speaks in the voice of a reference clip. To enable the
Sanskrit voice, drop a short (5–15 s) clean Sanskrit reference clip and its exact
transcript into `server/if5_refs/`:

```
server/if5_refs/sanskrit.wav      # mono, 24 kHz, clean Sanskrit speech
server/if5_refs/sanskrit.txt      # the exact Devanagari transcript of that clip
```

The voice **auto-appears** in the picker once both files exist (and the IndicF5
service on :8004 is up). No code change or restart flag needed — same mechanism
as the existing `if5-aanya` / `if5-aarav` voices.

## 2. `vagdhenu-sa-chant` — Sanskrit chanting (Vāgdhenu)

[Vāgdhenu](https://github.com/prathoshap/vagdhenu) (Apache-2.0) chants metered
ślokas with a melodic contour — MOS ~4.6, renders retroflex conjuncts faithfully.
It runs as an isolated microservice (`vagdhenu_service.py`) that shells out to the
model's `render.py`, exactly like the IndicF5 service.

**Deploy on the GPU box (CUDA 12.1, Python 3.10):**

```bash
# 1. Clone + install the model (its own venv, torch cu121, BigVGAN, weights)
git clone https://github.com/prathoshap/vagdhenu ~/vagdhenu
cd ~/vagdhenu && python3.10 -m venv .venv && bash scripts/setup.sh

# 2. Run the microservice (from the Prapthi server dir, any Python 3)
VAGDHENU_DIR=~/vagdhenu \
VAGDHENU_PY=~/vagdhenu/.venv/bin/python \
VAGDHENU_PORT=8006 \
python vagdhenu_service.py

# 3. Tell the main app to advertise the voice + where the service is
export VAGDHENU_ENABLED=1
export VAGDHENU_URL=http://127.0.0.1:8006
# (restart the main app so the /voices list picks it up)
```

Env vars the main app / service understand:

| Var | Default | Purpose |
|---|---|---|
| `VAGDHENU_ENABLED` | `0` | Advertise `vagdhenu-sa-chant` in `/voices` |
| `VAGDHENU_URL` | `http://127.0.0.1:8006` | Where the main app reaches the service |
| `VAGDHENU_DIR` | `~/vagdhenu` | Repo checkout (contains `src/render.py`) |
| `VAGDHENU_PY` | `<DIR>/.venv/bin/python` | Model venv interpreter |
| `VAGDHENU_PORT` | `8006` | Service listen port |
| `VAGDHENU_METER` | `anushtubh` | Default meter when a request omits one |

**Meter:** Vāgdhenu chants *metered verse*. Requests may pass `"meter"` (e.g.
`anushtubh`) in the `/speak` body; otherwise `VAGDHENU_METER` is used. Verse lines
are split into padas on newlines and daṇḍas (`।`, `॥`). Best for stotras / mantras
/ ślokas — not arbitrary prose.

Health check: `curl -s localhost:8006/health` → `{"status":"ok","loaded":true,…}`
(`loaded:false` means the repo/venv paths are wrong).
