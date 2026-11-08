"""A/B test for the Studio Clone tier: is a fine-tuned Qwen3-TTS voice better than
the cloning we already serve? Runs ON the training VM inside ~/vcl/.venv.

  ab_tools.py reference SPEAKER OUT    pick one real clip + its transcript as the shared reference
  ab_tools.py generate  SPEAKER SENTENCES OUT
                                       render the test set with every epoch checkpoint and with
                                       zero-shot Qwen3-TTS, into OUT/<system>/<id>_t<k>.wav
  ab_tools.py score     OUT SENTENCES  score every OUT/<system>/ (baselines included) -> report

Every system is cloned from the same OUT/reference.wav, so they compete on equal terms.
`real` holds other genuine clips of the speaker: its similarity is the ceiling the
metric can reach, so a system is judged against that, not against 1.0.
Whisper character error is meaningful for Hindi and English only; Telugu is listed
but must be judged by ear (Whisper mis-scripts it).
"""
from __future__ import annotations

import json
import random
import shutil
import sys
import unicodedata
from pathlib import Path

TAKES = 2          # the engines are stochastic; one take per sentence cannot rank them
# Qwen3-TTS emits 12.5 codec frames a second and by default stops only at 8192 frames
# (655 s). Outside its languages (te) it sometimes never ends a sentence: on 5 Nov four
# Telugu takes ran to 655 s, ~27 min each, and used up the night. Every test sentence
# is under 8 s, so cap at 32 s and count a clip that reaches the cap as a runaway.
MAX_NEW_TOKENS = 400
CAP_SECONDS = MAX_NEW_TOKENS / 12.5
REAL_CLIPS = 6
CER_TRUSTED = {"hi", "en"}


def _rows(spec: Path) -> list[dict]:
    return json.loads(spec.read_text(encoding="utf-8"))


def _voice(speaker: str):
    from voice_clone_lab.config import Config
    cfg = Config.load()
    return cfg, cfg.paths_for(speaker)


def cmd_reference(speaker: str, out: Path) -> None:
    import soundfile as sf
    from voice_clone_lab.utils import read_jsonl, resolve_artifact_path

    cfg, paths = _voice(speaker)
    pool = []
    for row in read_jsonl(paths.transcripts_jsonl):
        p, text = resolve_artifact_path(row["audio"]), str(row.get("text", "")).strip()
        if p.exists() and text:
            pool.append((sf.info(str(p)).duration, p, text))
    ref = [r for r in pool if 6.0 <= r[0] <= 12.0]
    if not ref:
        raise SystemExit("no 6-12 s clip with a transcript to use as the reference")
    ref.sort(key=lambda r: -len(r[2]))           # most words: best ICL prompt
    dur, path, text = ref[0]
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(path, out / "reference.wav")
    (out / "reference.json").write_text(json.dumps({"text": text, "seconds": round(dur, 2),
                                                     "source": str(path)}, ensure_ascii=False, indent=1))
    real = out / "real"
    real.mkdir(exist_ok=True)
    others = [r for r in pool if r[1] != path and r[0] >= 3.0]
    random.Random(0).shuffle(others)
    for i, (_, p, t) in enumerate(others[:REAL_CLIPS]):
        shutil.copy(p, real / f"real{i}.wav")
    print(f"reference: {dur:.1f}s  {text}")


def cmd_generate(speaker: str, spec: Path, out: Path) -> None:
    import gc
    import soundfile as sf
    import torch
    from voice_clone_lab.generate import _checkpoint_sort_key, load_model, resolve_attn_implementation

    cfg, paths = _voice(speaker)
    rows = _rows(spec)
    ref = json.loads((out / "reference.json").read_text(encoding="utf-8"))
    attn = resolve_attn_implementation(cfg)
    g = cfg.generation
    sampling = dict(do_sample=True, top_k=g.top_k, top_p=g.top_p, temperature=g.temperature,
                    max_new_tokens=MAX_NEW_TOKENS)

    systems = [(f"qwen-{c.name.replace('checkpoint-', '')}", c, "custom")
               for c in sorted((c for c in paths.checkpoints_dir.glob("checkpoint-*")
                                if (c / "config.json").exists()), key=_checkpoint_sort_key)]
    systems.append(("qwen-zeroshot", cfg.init_model_path(), "clone"))
    for name, model_path, mode in systems:
        d = out / name
        todo = [(r, k) for r in rows for k in range(1, TAKES + 1) if not (d / f"{r['id']}_t{k}.wav").exists()]
        if not todo:
            continue
        d.mkdir(parents=True, exist_ok=True)
        tts = load_model(model_path, cfg.project.device, attn)
        for r, k in todo:
            torch.manual_seed(1000 * k + rows.index(r))
            if mode == "custom":
                wavs, sr = tts.generate_custom_voice(text=r["text"], speaker=paths.speaker,
                                                     language=g.language, **sampling)
            else:
                wavs, sr = tts.generate_voice_clone(text=r["text"], language=g.language,
                                                    ref_audio=str(out / "reference.wav"),
                                                    ref_text=ref["text"], x_vector_only_mode=False,
                                                    **sampling)
            sf.write(d / f"{r['id']}_t{k}.wav", wavs[0], sr)
        print(f"{name}: {len(todo)} clips", flush=True)
        del tts
        gc.collect(); torch.cuda.empty_cache()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower()
    return "".join(c for c in s if not (unicodedata.category(c)[0] in "PSZ" or c.isspace()))


def _cer(ref: str, hyp: str) -> float:
    a, b = _norm(ref), _norm(hyp)
    if not a:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1] / len(a)


def cmd_score(out: Path, spec: Path) -> None:
    import librosa
    import numpy as np
    import torch
    from faster_whisper import WhisperModel
    from transformers import AutoFeatureExtractor, WavLMForXVector

    rows = {r["id"]: r for r in _rows(spec)}
    fe = AutoFeatureExtractor.from_pretrained("microsoft/wavlm-base-plus-sv")
    sv = WavLMForXVector.from_pretrained("microsoft/wavlm-base-plus-sv").cuda().eval()
    asr = WhisperModel("large-v3", device="cuda", compute_type="float16")

    def embed(p: Path):
        y, _ = librosa.load(str(p), sr=16000, mono=True)
        x = fe(y, sampling_rate=16000, return_tensors="pt").to("cuda")
        with torch.no_grad():
            e = sv(**x).embeddings[0]
        return torch.nn.functional.normalize(e, dim=-1)

    ref_e = embed(out / "reference.wav")
    report = {}
    for d in sorted(p for p in out.iterdir() if p.is_dir()):
        clips = sorted(d.glob("*.wav"))
        if not clips:
            continue
        per_lang: dict[str, dict[str, list]] = {}
        for c in clips:
            sim = float(ref_e @ embed(c))
            sid = c.stem.rsplit("_t", 1)[0]
            row = rows.get(sid)
            lang = row["lang"] if row else "real"
            bucket = per_lang.setdefault(lang, {"sim": [], "cer": [], "sec": [], "runaway": 0})
            bucket["sim"].append(sim)
            sec = librosa.get_duration(path=str(c))
            bucket["sec"].append(sec)
            bucket["runaway"] += row is not None and sec >= CAP_SECONDS - 0.5
            if row:
                segs, _ = asr.transcribe(str(c), language=row["lang"], beam_size=5)
                bucket["cer"].append(_cer(row["text"], " ".join(s.text for s in segs)))
        report[d.name] = {lang: {"clips": len(v["sim"]),
                                 "speaker_sim": round(float(np.mean(v["sim"])), 3),
                                 "cer": round(float(np.mean(v["cer"])), 3) if v["cer"] else None,
                                 "cer_trusted": lang in CER_TRUSTED,
                                 "seconds": round(float(np.mean(v["sec"])), 2),
                                 "runaway": int(v["runaway"])}
                          for lang, v in per_lang.items()}
        print(d.name, json.dumps(report[d.name], ensure_ascii=False), flush=True)

    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    langs = sorted({l for s in report.values() for l in s if l != "real"})
    ceiling = report.get("real", {}).get("real", {}).get("speaker_sim")
    lines = [f"# A/B report: {out.name}", "",
             f"Speaker similarity ceiling (other real clips of this voice): **{ceiling}**. "
             "Character error is trusted for hi/en only; judge te by ear. "
             f"Runaways = takes that never ended and hit the {CAP_SECONDS:.0f} s cap.", "",
             "| system | " + " | ".join(f"{l} sim | {l} CER" for l in langs) + " | runaways |",
             "|---|" + "---|---|" * len(langs) + "---|"]
    for name, s in report.items():
        if name == "real":
            continue
        cells = []
        for l in langs:
            v = s.get(l)
            cells += ([f"{v['speaker_sim']:.3f}",
                       "-" if v["cer"] is None else f"{v['cer']:.1%}{'' if v['cer_trusted'] else ' ?'}"]
                      if v else ["", ""])
        runs = sum(v.get("runaway", 0) for l, v in s.items() if l != "real")
        lines.append(f"| {name} | " + " | ".join(cells) + f" | {runs} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    cmd, *a = sys.argv[1:] or ["-h"]
    if cmd == "reference" and len(a) == 2:
        cmd_reference(a[0], Path(a[1]).expanduser())
    elif cmd == "generate" and len(a) == 3:
        cmd_generate(a[0], Path(a[1]), Path(a[2]).expanduser())
    elif cmd == "score" and len(a) == 2:
        cmd_score(Path(a[0]).expanduser(), Path(a[1]))
    else:
        raise SystemExit(__doc__)
