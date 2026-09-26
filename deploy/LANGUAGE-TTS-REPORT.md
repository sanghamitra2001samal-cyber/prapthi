# Prapthi — best TTS engine per language (2026 research report)

Compiled 2026-08-18. Grounded in current (2026) open-source TTS research + what's
already in your codebase + your own measured emotion findings.

## The winning stack (short version)

| Role | Engine | Params | GPU? |
|---|---|---|---|
| **Indic workhorse WITH emotion** (19 Indian langs incl. Telugu, Sanskrit speech) | **svara-TTS** `kenpath/svara-tts-v1` | 3B | Yes, 16GB+ |
| **Sanskrit CHANTING** (śloka/pārāyaṇa) | **Vāgdhenu** (IISc) — *already in your `vagdhenu_service.py`* | ~337M | Small — maybe CPU-OK |
| **Premium English / cross-lingual emotion + cloning** | **IndexTTS-2.5** | ~1B | Yes, ~6GB |
| **Max-quality Indic (no emotion needed)** | **IndicF5** (AI4Bharat, 1417h) | — | Yes |
| **Chinese (Mandarin)** | **CosyVoice2-0.5B** | 0.5B | Yes (small) |
| **Fast CPU fallback (what you run now)** | Kokoro (82M) / Piper | tiny | **No — CPU** |

## Per-language recommendation

| Language | Best for emotion | Best for quality | You have now |
|---|---|---|---|
| **English** (US/UK/IN) | IndexTTS-2.5 | IndexTTS-2.5 | Kokoro, Piper (no emotion) |
| **Chinese** | CosyVoice2 | CosyVoice2 | Kokoro-zh (no emotion) |
| **Hindi** | svara-TTS / IndexTTS-2 | IndicF5 | Kokoro/Piper/Parler-hi |
| **Telugu** ⭐ | **svara-TTS** (120h — strong emotion) | IndicF5 | Piper-te, Parler-te (no emotion) |
| **Tamil** | svara-TTS | IndicF5 | MMS-ta, Parler-ta (no emotion) |
| **Kannada** | svara-TTS | IndicF5 | MMS-kn, Parler-kn |
| **Malayalam** | svara-TTS | IndicF5 | Piper-ml, Parler-ml |
| **Bengali** | svara-TTS | IndicF5 | MMS-bn, Parler-bn |
| **Gujarati** | svara-TTS | IndicF5 | MMS-gu, Parler-gu |
| **Marathi** | svara-TTS | IndicF5 | MMS-mr, Parler-mr |
| **Punjabi** | svara-TTS | IndicF5 | MMS-pa, Parler-pa |
| **Assamese** | svara-TTS | IndicF5 | Parler-as |
| **Odia** | svara-TTS | IndicF5 | Parler-or |
| **Sanskrit (speech)** | svara-TTS (51h — weaker) | svara-TTS | Parler-sa (no emotion) |
| **Sanskrit (chanting)** ⭐ | **Vāgdhenu** | **Vāgdhenu** (MOS 4.6) | **Vāgdhenu built, not deployed** |
| **Bhojpuri / Maithili / Magahi / Chhattisgarhi** | svara-TTS | svara-TTS | Parler (some) |
| **Bodo / Dogri / Manipuri / Nepali** | svara-TTS | svara-TTS | Parler (some) |

⭐ = the two you specifically asked about (Telugu, Sanskrit chanting).

## Sanskrit chanting — the special request (detailed)

**Vāgdhenu** is the answer, and you already integrated it (`server/vagdhenu_service.py`):
a flow-matching DiT (~337M) + BigVGAN-v2 vocoder, **vṛtta (meter)-aware**, trained on a
purpose-recorded single-speaker Sanskrit chant corpus (~5h), expert MOS ≈ **4.6**. It
renders faithful chanted pārāyaṇa recitation with retroflex conjuncts, the three sibilants,
aspiration, visarga sandhi, and homorganic anusvāra kept distinct. This is *purpose-built
for chanting* — no general TTS matches it for śloka recitation.

**Two important caveats:**
1. **Non-Vedic only.** The author explicitly limits it to non-Vedic chants (śloka /
   stotra / pārāyaṇa). Strict **Vedic** chanting with udātta/anudātta/svarita pitch
   accents is a harder, largely unsolved problem — Vāgdhenu does *chant* prosody, not the
   three-tone Vedic accent system. If you need true Vedic accent, that's a research gap;
   set that expectation.
2. **~337M is SMALL** — roughly 10× lighter than svara-TTS (3B). This is the key opening:
   **Vāgdhenu may run acceptably on the current CPU box** (seconds per clip, not minutes),
   unlike the 3B engines. And chanting content is usually **fixed** (known ślokas) → you
   can **pre-generate a chant library once, cache it, and serve with zero ongoing GPU.**
   This is the one "perfect Sanskrit chanting" win you might get *without* a GPU.

## The unavoidable GPU reality (unchanged)

- **svara-TTS (3B), IndexTTS-2, CosyVoice2, IndicF5 all need a GPU.** Your GCP account has
  **0 GPU quota** (auto-denied, verified by a real launch attempt: *"Quota
  GPUS_ALL_REGIONS exceeded. Limit 0.0 globally"*). No CPU path for these.
- **Kokoro / Piper** run on CPU — that's your current 133 voices — but **no real emotion**.
- **Vāgdhenu (337M)** is the borderline case worth testing on CPU.

## Recommended plan

1. **Sanskrit chanting first (possible NOW, no GPU):** carefully test Vāgdhenu on the CPU
   box (it's small). If it runs, pre-generate a śloka chant library → cache → serve. This
   delivers the Sanskrit chanting you asked for without waiting on a GPU. *(Test with
   resource limits so the live site isn't put at risk.)*
2. **Everything else (Telugu emotion, Hindi/Tamil emotion, English emotion):** needs a GPU.
   Rent one (RunPod L4/A5000) → deploy **svara-TTS** (covers 19 Indic incl. Telugu +
   Sanskrit speech, with emotion) + **IndexTTS-2** (English). Wire into `engine.py`,
   turn OFF the DSP pitch hack for these, run the per-language emotion audit.
3. **Validate per your own methodology:** measure each language *in its own language*,
   5 samples × 2 sentences per emotion, separation ratio ≥1.0 with correct happy>sad
   direction. Especially Telugu and Sanskrit before declaring "perfect."

## Sources
- svara-TTS: huggingface.co/kenpath/svara-tts-v1 · blog/kenpath/svara-tts-open-multilingual-speech-for-india
- Vāgdhenu: prathosh.in/vagdhenu · (IISc, Prof. Prathosh A.P.)
- IndexTTS-2: github.com/index-tts/index-tts · arXiv:2506.21619
- IndicF5: huggingface.co/ai4bharat/IndicF5 (1417h, 11 langs)
- CosyVoice2: FunAudioLLM/CosyVoice2-0.5B
- 2026 benchmark: marktechpost.com/2026/05/30/best-text-to-speech-tts-models-in-2026
