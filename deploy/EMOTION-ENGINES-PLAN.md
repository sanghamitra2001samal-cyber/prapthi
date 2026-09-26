# Real emotion for every language — the plan

Updated 2026-08-18 after vigorous research. **Everything here is GPU-blocked.**

## The verdict — which engine for what

| Need | Engine | Why |
|---|---|---|
| **Indic emotion (Telugu, Sanskrit, + 17 more)** | **svara-TTS** (`kenpath/svara-tts-v1`) | Purpose-built for 19 Indian langs WITH emotion tags; Telugu ~120h, Sanskrit ~51h training. This is the one you asked for. |
| English / cross-lingual emotion, voice cloning | IndexTTS-2.5 | Best measured emotional fidelity (your Aug-3 audit: 3.95); 8-dim emotion vector; zero-shot clone from a reference clip. |
| Current 133 voices (Kokoro/Piper/MMS/Parler) | keep as-is | Fast on CPU, but **no real emotion** — the dropdown is a DSP pitch trick. |

**Recommendation:** deploy **svara-TTS as the primary emotion engine** (covers your Indic-heavy
catalog incl. Sanskrit + Telugu), and IndexTTS-2 as a second for premium English/cloning.

## svara-TTS specifics

- Model: `kenpath/svara-tts-v1` (3B params). Inference: github.com/Kenpath/svara-tts-inference.
- **19 languages:** Hindi, Bengali, Marathi, **Telugu**, Kannada, Bhojpuri, Magahi,
  Chhattisgarhi, Maithili, Assamese, Bodo, Dogri, Gujarati, Malayalam, Punjabi, Tamil,
  Indian English, Nepali, **Sanskrit**.
- **Emotion:** sentence-END tags — `<happy> <sad> <anger> <fear> <surprise>`.
- **Caveat 1 — emotion strength varies by data:** Telugu (120h) will emote clearly;
  **Sanskrit (51h) will be weaker** — set expectations, may need extra fine-tuning data.
- **Caveat 2 — LICENSE unverified.** Check huggingface.co/kenpath/svara-tts-v1 for a
  commercial-use license BEFORE shipping it in a paid product. Do not skip this.
- Needs a GPU (3B params). svara was trained on RunPod → RunPod L4/A10 is a proven target.

## The blocker (unchanged)

- **GCP GPU is auto-denied.** Quota requests filed 2026-08-18 for `GPUS-ALL-REGIONS`
  and `NVIDIA-L4-GPUS` (asia-south1) → Google granted **0** (new account, no billing
  history). Not permanent. Options: (a) GCP Support escalation case, (b) build ~30d
  billing history then retry, (c) rent a GPU elsewhere.
- **Fastest path = rent a GPU** (RunPod / Lambda / Vast.ai). No quota gate. svara-TTS
  install script (`svara-tts-install.sh`) and IndexTTS-2 script (`indextts2-install.sh`)
  are ready to run on it.

## Deploy steps once a GPU exists

1. GPU box (rented or GCP once unblocked).
2. `bash svara-tts-install.sh` (clone, venv, download 3B model). **Verify license first.**
3. **Microservice** `svara_service.py` on `127.0.0.1:8012` (mirror the existing
   `chatterbox_service.py` pattern): load svara once, `POST /synthesize
   {text, voiceId, emotion, lang}` → append the `<emotion>` tag at sentence end → wav.
   Unload after idle (box OOMs if everything stays hot — gpu-headroom finding).
4. **Engine class** `SvaraEngine` in `engine.py`: register `svara-<lang>-<name>` voice ids;
   map the frontend emotion dropdown → svara tags:
   Natural→(none) · Energetic/Happy→`<happy>` · Emotional/Sad→`<sad>` · Angry→`<anger>` ·
   (Calm/Professional→none or `<sad>` softly · Storytelling→`<surprise>` lightly).
5. Add svara voices to `/api/voices` — the frontend renders whatever the API returns, so
   they show up automatically (names cleaned of engine tags, as already built).
6. Turn OFF the DSP pitch hack for svara/idx voices (real emotion must not be flattened).
7. For Sanskrit specifically: if emotion is too weak, gather more Sanskrit emotion-labelled
   data and LoRA-tune — but note the Tamil-LoRA attempt failed on Parler, so validate on
   svara before investing (svara is a different, emotion-native base, so more promising).

## Vigorous check before shipping (do NOT skip)

Per your voice-eval methodology: measure each language **in its own language**, 5 samples
× 2 sentences per emotion, separation ratio = between-emotion distance / within-emotion
scatter, with correct happy>sad pitch direction. A score ≥1.0 with correct direction =
audible. Run this for Telugu and Sanskrit specifically before declaring emotion "perfect."

Sources: huggingface.co/kenpath/svara-tts-v1, huggingface.co/blog/kenpath/svara-tts-open-multilingual-speech-for-india,
github.com/index-tts/index-tts, IndexTTS2 arXiv:2506.21619.
