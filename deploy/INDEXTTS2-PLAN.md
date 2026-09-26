# Adding real emotion (IndexTTS-2) — integration plan

Prepared 2026-08-17. **Status: BLOCKED on GPU. Nothing here is tested.**

## Why this exists

Your own measurements (emotion-truth, 2026-08-03) proved **IndexTTS-2 is the only
engine that genuinely emotes** (separation score 3.95 "audible"; Kokoro/Piper/MMS/
Parler all score <1.0 — their "emotion" is a fake pitch/speed multiplier). 2026 SOTA
research confirms IndexTTS-2 is still the best for emotion. So real emotion = deploy
IndexTTS-2. There is no CPU path — it needs a GPU.

## The two hard blockers

1. **No GPU.** L4 quota in asia-south1 is **0** and `GPUS_ALL_REGIONS` is 0 — Google
   hasn't approved the request. New GCP accounts are often denied GPU on the first ask.
   **Action for the user:** in the console, re-file the L4 quota request with a
   justification; if denied, contact GCP support or let the billing account age a few
   weeks then retry. Everything below waits on this.

2. **The integration code is GONE.** The deployed backend (Jul 2) defines only
   Kokoro/Piper/MMS/Parler/Chatterbox engines — **no IndexTTS engine**. The IndexTTS-2
   wiring was written on the AWS box and died with it. So this is a **rebuild**, not a
   redeploy.

## What IndexTTS-2 actually is (matters for the design)

- **Zero-shot cloning** model: it clones a voice from a 5–10s **reference audio clip**
  (`spk_audio_prompt`). It does NOT have pre-baked named voices like Kokoro/Piper.
  → So each "IndexTTS voice" in the catalog = a curated reference clip.
- **Emotion**: an **8-dim vector** (8 sliders 0.0–1.4, sum ≤ 1.5) OR a natural-language
  description. This is the real, felt emotion control.
- API: `from indextts.infer_v2 import IndexTTS2` →
  `tts.infer(spk_audio_prompt="ref.wav", text="…", output_path="out.wav", emo_vector=[...])`
- Needs Python 3.10/3.11, `uv`, ffmpeg, libsndfile1, ~6 GB VRAM.

## Deploy steps (once a GPU box exists)

1. **Get the GPU box.** The existing `gcp-deploy.sh` targets `g2-standard-8` + L4 —
   use it once quota is granted (or add a GPU to `prapthi-1` and reprovision).
2. **Install IndexTTS-2:** run `indextts2-install.sh` on the box (clone repo, `uv sync`,
   download `IndexTeam/IndexTTS-2.5`, smoke-test).
3. **Reference clips:** collect 5–10s clean clips for each IndexTTS voice you want
   (English + Indian languages). These define the voices. Store in
   `~/prapthi/index-tts/refs/<voiceid>.wav`.
4. **Microservice** `indextts_service.py` on `127.0.0.1:8011` (mirror the pattern of the
   existing `chatterbox_service.py` / `if5_service.py`): load IndexTTS2 once, expose
   `POST /synthesize {text, voiceId, emotion|emo_vector}` → wav. Keep it on the GPU;
   unload after idle (see gpu-headroom findings — the box OOMs if everything stays hot).
5. **Engine class** `IndexTTSEngine` in `engine.py`: register `idx-*` voice ids mapped to
   their reference clips; on synth, POST to :8011 with the emotion vector. Add these
   voices to the catalog with an `idx-` prefix so the frontend picks them up (the site
   already renders whatever `/api/voices` returns).
6. **Emotion mapping:** map the site's emotion dropdown (Natural/Calm/Energetic/…) to
   IndexTTS-2 8-dim vectors. Approx starting points (tune by ear):
   - Natural = neutral (all ~0)
   - Calm = low arousal, slight "calm" dim
   - Energetic/Happy = "happy" dim ~0.9
   - Emotional/Sad = "sad" dim ~0.9
   - Storytelling = mild "surprise"/"calm" blend
   - Professional = neutral, slightly lowered pitch
7. **Turn OFF the DSP hack for IndexTTS:** set `_emo_dsp_scale('idx-…') = 0.0` (the
   Aug-3 fix, which is also NOT in the deployed code — it was on AWS). The DSP pitch
   multiplier must not be layered over IndexTTS-2's real expression or it flattens it.
8. **Check the RNNoise denoise** in `_finalize` — the open lead was that it compresses
   loudness dynamics and may be flattening emotion platform-wide. Test with it bypassed
   for IndexTTS output.

## Reality check

This is a multi-day rebuild (reference-clip curation is the slow part), fully gated on a
GPU that Google hasn't granted. Do NOT run IndexTTS-2 on the current CPU box — it would
be minutes per clip and prove nothing.

## Alternatives if the L4 quota stays blocked

- **RunPod / Lambda / Vast.ai**: rent an L4/A10/3090 by the hour, deploy IndexTTS-2
  there, point `api.prapthi.ai` at it. Sidesteps Google's quota entirely. Likely the
  fastest route to real emotion.
- **CosyVoice2**: lower latency, but emotion is not its strength — not a substitute.

Sources: index-tts/index-tts (GitHub), IndexTeam/IndexTTS-2.5 (Hugging Face),
IndexTTS2 paper arXiv:2506.21619.
