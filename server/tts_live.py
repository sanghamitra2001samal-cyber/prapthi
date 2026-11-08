"""Live text-to-speech over a WebSocket: text goes in while it is still being
written (an LLM's tokens, say), audio comes out phrase by phrase.

Why phrases and not tokens. A voice decides its rhythm and stress from the
words around each word; handed two or three tokens at a time it reads every
fragment flat and the joins are audible. Commercial streaming TTS waits for a
short phrase for the same reason. So the first phrase is cut early — the first
comma, or a handful of words — and later phrases grow, which keeps the next
one ready before the current one finishes playing.

Audio goes out as raw 16-bit PCM, not mp3: an mp3 encoder adds its own delay
and a silent priming frame at the start of every chunk.

Protocol (JSON text frames unless noted)
  client -> {"type": "start", "voiceId": "...", "emotion"?, "intensity"?,
             "rate"?, "pitch"?, "volume"?}            must be the first frame
  client -> {"type": "text", "text": "..."}           any size, any split
  client -> {"type": "flush"}                         speak what is buffered
  client -> {"type": "end"}                           no more text
  server -> {"type": "ready", "encoding": "pcm_s16le", "channels": 1}
  server -> {"type": "audio", "seq", "sampleRate", "bytes", "text", ...}
            followed by one binary frame holding exactly `bytes` of PCM
  server -> {"type": "done", "phrases", "charged"}  then the socket closes
  server -> {"type": "error", "message", "code"?}   then the socket closes
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import time

import numpy as np
import soundfile as sf
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

# A client that goes quiet this long, with nothing left to speak, is closed.
IDLE_TIMEOUT_S = 120.0
# Text the client may have sent that is not yet spoken (buffered or queued).
MAX_PENDING_CHARS = 5000
# Leading silence kept on the first phrase. Engines pad every take with ~60 ms
# (engine._polish_wav); at the very start of speech that is pure latency.
FIRST_LEAD_S = 0.02


# --------------------------------------------------------------------------- #
# Cutting a stream of text into phrases
# --------------------------------------------------------------------------- #
_SENTENCE_END = set(".!?।॥")
_CLAUSE_END = set(",;:—–")
# A full stop after a title never ends a sentence ("Dr. Sharma"). After other
# abbreviations it does when a capital follows ("at 10 a.m. Please call").
_TITLES = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "prof", "no", "rs", "vs"}
_ABBREV = {"etc", "approx", "dept", "govt", "ltd", "pvt", "inc", "co", "e.g",
           "i.e", "a.m", "p.m", "u.s"}
# Words that belong to the number before them ("₹ 2,450", "10:30 बजे"):
# never cut between the two, or the number is read without its unit.
_GLUE_AFTER_NUMBER = {"बजे", "बजकर", "%", "am", "pm", "a.m.", "p.m.", "lakh",
                      "lakhs", "crore", "crores", "लाख", "करोड़", "rupees",
                      "rupee", "रुपये", "रुपया", "रुपए", "hours", "minutes",
                      "मिनट", "घंटे", "km", "kg"}
_GLUE_BEFORE_NUMBER = {"₹", "rs", "rs.", "inr", "$", "+91", "no.", "number"}


# Hindi and Bhojpuri put postpositions and auxiliaries after the word they
# belong to. Cutting before one ("प्राप्ति ए आई | से बोल") strands it at the
# start of the next phrase, which sounds broken; cut before a content word.
_NO_CUT_BEFORE = {"से", "के", "की", "का", "को", "में", "पर", "ने", "तक", "है",
                  "हैं", "हूँ", "हो", "था", "थी", "थे", "रहा", "रही", "रहे",
                  "गया", "गई", "गए", "दिया", "जी", "भी", "ही", "तो", "ले", "बा",
                  "बानी", "बाड़े", "रहल", "सकते", "सकता", "सकती", "चाहिए"}
# When a phrase must be cut with no punctuation to cut at, just before one of
# these is where a speaker would breathe.
_CONJUNCTIONS = {"और", "लेकिन", "पर", "मगर", "क्योंकि", "कि", "तो", "या", "जब",
                 "अगर", "ताकि", "बाकिर", "आउर", "अउर", "and", "but", "because",
                 "so", "or", "which", "who", "when", "if", "while", "although",
                 "since", "then", "until", "unless", "where", "whereas"}
# The genitive always leads into what follows ("के लिए", "का जवाब").
_NO_CUT_AFTER = {"के", "की", "का", "रउआ", "हमार", "राउर"}


def _ends_sentence(token: str, nxt: str) -> bool:
    if token[-1] not in _SENTENCE_END:
        return False
    if token[-1] != ".":
        return True
    core = token.rstrip(".").lower()
    if core in _TITLES:
        return False
    if len(core) == 1 or core in _ABBREV or "." in core:
        return nxt[:1].isupper()
    return True


class PhraseSplitter:
    """Collects streamed text and hands back phrases worth speaking.

    A boundary only counts once whitespace follows it, so "2,450" and "10:30"
    are never split while their digits are still arriving.
    """

    def __init__(self, min_chars: int = 2, first_words: int = 2,
                 first_max_words: int = 6, clause_words: int = 6,
                 max_chars: int = 240):
        self.min_chars = min_chars
        self.first_words = first_words
        self.first_max_words = first_max_words
        self.clause_words = clause_words
        self.max_chars = max_chars
        self.buf = ""
        self.emitted = 0
        self.last_len = 0
        self.spoken = 0

    def _budget(self) -> int:
        """Longest next phrase: twice the last one, or everything spoken so
        far (that much audio is already queued ahead of the listener),
        whichever is more. A longer phrase may not be ready before the one
        playing ends. MEASURED locally: with no limit a 13-character phrase
        followed by an 80-character one left 5.9 s of silence."""
        return min(self.max_chars, max(2 * self.last_len, self.spoken, 40))

    def feed(self, text: str) -> list[str]:
        self.buf += text
        out = []
        while True:
            cut = self._find_cut()
            if cut is None:
                return out
            phrase, self.buf = self.buf[:cut].strip(), self.buf[cut:].lstrip()
            if phrase:
                out.append(phrase)
                self.emitted += 1
                self.last_len = len(phrase)
                self.spoken += len(phrase)

    def flush(self) -> list[str]:
        phrase, self.buf = self.buf.strip(), ""
        if not phrase:
            return []
        self.emitted += 1
        self.last_len = len(phrase)
        self.spoken += len(phrase)
        return [phrase]

    def _find_cut(self) -> int | None:
        buf = self.buf
        first = self.emitted == 0
        budget = self._budget()
        # Offsets where a phrase could end: at a pause the writer put in, or
        # (failing that) between two words that may be parted.
        words, word_cuts, clause_cuts, soft_cuts, over = 0, [], [], [], False
        for m in re.finditer(r"\S+(?=\s)", buf):
            tok = m.group(0)
            words += 1
            end = m.end()
            if not first and len(buf[:end].strip()) > budget:
                over = True
                break
            nxt = re.match(r"\s+(\S+)", buf[end:])
            nxt_tok = nxt.group(1) if nxt else ""
            last = tok[-1]
            kind = None
            if "\n" in buf[end:end + (nxt.end() if nxt else len(buf) - end)]:
                kind = "sentence"
            elif _ends_sentence(tok, nxt_tok):
                kind = "sentence"
            elif last in _CLAUSE_END:
                kind = "clause"
            long_enough = len(buf[:end].strip()) >= self.min_chars
            if kind and long_enough:
                # A finished sentence may be a single word ("Hi!"); a clause
                # needs a few, or the voice reads one word and pauses.
                need = (1 if kind == "sentence" else
                        self.first_words if first else self.clause_words)
                if words >= need:
                    return end
                clause_cuts.append(end)
            # Judge a word gap only once the next word is complete: "सक" may
            # still become "सकती", which must not start a phrase.
            nxt_done = bool(re.match(r"\s+\S+\s", buf[end:]))
            if nxt_done and self._safe_word_cut(tok, nxt_tok) and long_enough:
                word_cuts.append(end)
                if nxt_tok.lower() in _CONJUNCTIONS:
                    soft_cuts.append(end)
        if (words >= self.first_max_words) if first else over:
            # Out of patience: a pause the writer put in beats a word gap.
            if clause_cuts:
                return clause_cuts[-1]
            if soft_cuts:
                return soft_cuts[-1]
            if word_cuts:
                return word_cuts[-1]
        return None

    @staticmethod
    def _safe_word_cut(tok: str, nxt: str) -> bool:
        if not nxt:
            return False
        if (tok.lower() in _GLUE_BEFORE_NUMBER or tok in _NO_CUT_AFTER
                or nxt.rstrip("।,.!?") in _NO_CUT_BEFORE):
            return False
        if tok[-1].isdigit() and nxt.lower() in _GLUE_AFTER_NUMBER:
            return False
        # A number stays with the word before it ("सुबह 10:30", "of ₹2,450").
        if nxt[0].isdigit() or nxt[0] in "₹$+":
            return False
        return True


# --------------------------------------------------------------------------- #
# Audio helpers
# --------------------------------------------------------------------------- #
def _wav_to_pcm(wav: bytes, trim_lead: bool) -> tuple[bytes, int]:
    y, sr = sf.read(io.BytesIO(wav), dtype="int16", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1).astype(np.int16)
    if trim_lead and len(y):
        loud = np.flatnonzero(np.abs(y) > 300)
        if len(loud):
            start = max(0, int(loud[0]) - int(sr * FIRST_LEAD_S))
            y = y[start:]
    return y.astype("<i2").tobytes(), int(sr)


# --------------------------------------------------------------------------- #
# The endpoint
# --------------------------------------------------------------------------- #
def routes(app) -> list[WebSocketRoute]:
    """`app` is the app module; passed in rather than imported, because the
    app module imports this one."""
    from starlette.concurrency import run_in_threadpool
    import cache
    import db
    import emotion as emotion_mod
    import entitlements

    allowed = ({o.strip() for o in app.ALLOWED_ORIGIN.split(",") if o.strip()}
               if app.ALLOWED_ORIGIN != "*" else None)

    async def _error(ws: WebSocket, message: str, code: str = "") -> None:
        body = {"type": "error", "message": message}
        if code:
            body["code"] = code
        try:
            await ws.send_json(body)
            await ws.close()
        except Exception:
            pass

    async def tts_live(ws: WebSocket) -> None:
        origin = ws.headers.get("origin")
        if allowed is not None and origin and origin not in allowed:
            await ws.close(code=1008)
            return
        user = await app._current_user(ws)
        if not user:
            await ws.close(code=1008)
            return
        if app._rate_limited(app._client_ip(ws)):
            await ws.close(code=1013)
            return
        await ws.accept()

        try:
            start = json.loads(await asyncio.wait_for(ws.receive_text(), 15))
        except (asyncio.TimeoutError, ValueError, KeyError, WebSocketDisconnect):
            await _error(ws, "send a start message first")
            return
        if not isinstance(start, dict) or start.get("type") != "start":
            await _error(ws, "send a start message first")
            return

        voice_id = str(start.get("voiceId", "")).strip()
        if voice_id == "vagdhenu-sa-chant":
            # Metre is found from the whole verse; it cannot be spoken in pieces.
            await _error(ws, "chanting needs the whole verse; use /synthesize")
            return
        clone = if5clone = None
        if voice_id.startswith("if5clone:"):
            if5clone = await db.get_clone(voice_id.split(":", 1)[1], user["email"])
        elif voice_id.startswith("clone:"):
            clone = await db.get_clone(voice_id.split(":", 1)[1], user["email"])
        known = (if5clone or clone
                 or (voice_id.startswith("if5-") and app._if5_ref(voice_id))
                 or app._voice_owner(voice_id)[0])
        if not known:
            await _error(ws, "unknown voice")
            return
        account = await db.get_account(user["email"])
        if not entitlements.may_use_voice(account, voice_id):
            await _error(ws, entitlements.UPGRADE_VOICE, "upgrade_required")
            return

        try:
            rate = float(start.get("rate", 1.0))
            pitch = float(start.get("pitch", 1.0))
            volume = float(start.get("volume", 1.0))
            intensity = max(0.0, min(2.0, float(start.get("intensity", 1.0))))
        except (TypeError, ValueError):
            await _error(ws, "rate, pitch, volume and intensity must be numbers")
            return
        emotion = emotion_mod.normalize(str(start.get("emotion", "neutral")))

        svara = not (clone or if5clone) and app._voice_owner(voice_id)[0] == "SvaraEngine"
        lock = app._svara_sem if svara else app._synth_lock
        # svara is slower than real time and the GPU batches, so it renders
        # three phrases at once; below ~20 characters it mumbles.
        ahead = asyncio.Semaphore(3 if svara else 1)
        splitter = PhraseSplitter(min_chars=20) if svara else PhraseSplitter()
        free = bool(user.get("is_admin"))

        state = {"charged": 0, "phrases": 0, "failed": None, "first_text": None,
                 "pending": 0}
        order: asyncio.Queue = asyncio.Queue()

        async def render(seq: int, phrase: str):
            """One phrase -> (pcm, sample rate, info). Charged on a cache miss
            and refunded if the engine fails, like /synthesize."""
            async with ahead:
                emo = emotion
                if emo == "auto":
                    runs = emotion_mod.detect(phrase)
                    emo = runs[0][1] if runs else "neutral"
                text = app._prepare_text(phrase, voice_id, clone)
                cache_vid = voice_id
                if emo != "neutral":
                    cache_vid = f"{voice_id}@{emo}"
                    if abs(intensity - 1.0) > 1e-3:
                        cache_vid += f"#{intensity:.2f}"
                args = (cache_vid, text, rate, pitch, volume)
                t0 = time.monotonic()
                hit = cache.get(*args, "wav")
                if hit:
                    wav, cached = hit[0], True
                else:
                    cached, charge = False, 0
                    if app._synth_waiting >= app._MAX_QUEUE:
                        raise _Refused("server busy, please try again shortly", "busy")
                    charge = 0 if free else len(phrase)
                    if charge:
                        await db.reset_period_if_due(user["email"])
                        ok, _left = await db.consume_chars(user["email"], charge)
                        if not ok:
                            raise _Refused("You have used your monthly characters. "
                                           "Upgrade your plan to carry on.",
                                           "quota_exceeded")
                    app._synth_waiting += 1
                    try:
                        r_, p_, v_ = app._emotion_prosody(emo, intensity, rate, pitch, volume)
                        r_ = app._engine_pace(voice_id, r_)
                        async with lock:
                            wav, _m = await app._render_take(
                                voice_id, text, emo, r_, p_, v_, "wav",
                                sliders=(rate, pitch, volume), intensity=intensity,
                                clone=clone, if5clone=if5clone)
                    except BaseException:
                        if charge:
                            try:
                                await db.refund_chars(user["email"], charge)
                            except Exception as e:  # pragma: no cover
                                print(f"[voxforge] live refund failed: {e!r}")
                        raise
                    finally:
                        app._synth_waiting -= 1
                    state["charged"] += charge
                    cache.put(*args, wav, "audio/wav")
                pcm, sr = await run_in_threadpool(_wav_to_pcm, wav, seq == 0)
                return pcm, sr, {"text": phrase, "cached": cached,
                                 "renderMs": round((time.monotonic() - t0) * 1000),
                                 "_charge": 0 if cached else charge}

        def speak(phrases: list[str]) -> None:
            for p in phrases:
                seq = state["phrases"]
                state["phrases"] += 1
                state["pending"] += len(p)
                order.put_nowait((seq, len(p), asyncio.create_task(render(seq, p))))

        async def sender() -> None:
            while True:
                item = await order.get()
                if item is None:
                    return
                seq, n, task = item
                try:
                    pcm, sr, info = await task
                except _Refused as e:
                    state["failed"] = (str(e), e.code)
                    return
                except Exception as e:
                    print(f"[voxforge] live synthesis error: {e!r}")
                    msg = (str(e) if isinstance(e, app.EngineError)
                           else "synthesis failed, please try again")
                    state["failed"] = (msg, "")
                    return
                state["pending"] -= n
                info.pop("_charge", None)
                head = {"type": "audio", "seq": seq, "sampleRate": sr,
                        "bytes": len(pcm), **info}
                if seq == 0 and state["first_text"] is not None:
                    head["sinceFirstTextMs"] = round(
                        (time.monotonic() - state["first_text"]) * 1000)
                await ws.send_text(json.dumps(head, ensure_ascii=False))
                await ws.send_bytes(pcm)

        await ws.send_json({"type": "ready", "encoding": "pcm_s16le", "channels": 1})
        out = asyncio.create_task(sender())
        try:
            while True:
                recv = asyncio.ensure_future(ws.receive())
                done, _ = await asyncio.wait(
                    {recv, out}, timeout=IDLE_TIMEOUT_S,
                    return_when=asyncio.FIRST_COMPLETED)
                if out in done:          # a phrase failed; stop taking text
                    recv.cancel()
                    break
                if not done:
                    recv.cancel()
                    if order.empty() and state["pending"] == 0:
                        await _error(ws, "idle for too long", "idle")
                        return
                    continue
                frame = recv.result()
                if frame.get("type") == "websocket.disconnect":
                    return
                try:
                    msg = json.loads(frame.get("text") or "")
                except ValueError:
                    await _error(ws, "messages must be JSON")
                    return
                kind = msg.get("type") if isinstance(msg, dict) else None
                if kind == "text":
                    piece = str(msg.get("text", ""))
                    if state["first_text"] is None and piece.strip():
                        state["first_text"] = time.monotonic()
                    waiting = len(splitter.buf) + state["pending"] + len(piece)
                    if waiting > MAX_PENDING_CHARS:
                        await _error(ws, "too much text waiting to be spoken")
                        return
                    speak(splitter.feed(piece))
                elif kind == "flush":
                    speak(splitter.flush())
                elif kind == "end":
                    speak(splitter.flush())
                    order.put_nowait(None)
                    await asyncio.wait({out})
                    break
                else:
                    await _error(ws, f"unknown message type {kind!r}")
                    return
            if out.done() and not out.cancelled() and out.exception():
                return                   # the socket went away mid-send
            if state["failed"]:
                await _error(ws, *state["failed"])
                return
            await ws.send_json({"type": "done", "phrases": state["phrases"],
                                "charged": state["charged"]})
            await ws.close()
        except WebSocketDisconnect:
            pass
        finally:
            if not out.done():
                out.cancel()
            # Phrases nobody will hear: stop the ones still rendering (their
            # refunds run as they unwind) and hand back the ones that finished.
            while not order.empty():
                item = order.get_nowait()
                if item is None:
                    continue
                task = item[2]
                if not task.done():
                    task.cancel()
                elif not task.cancelled() and not task.exception():
                    charge = task.result()[2].get("_charge", 0)
                    if charge:
                        try:
                            await db.refund_chars(user["email"], charge)
                        except Exception as e:  # pragma: no cover
                            print(f"[voxforge] live refund failed: {e!r}")

    return [WebSocketRoute("/tts/live", tts_live)]


class _Refused(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code
