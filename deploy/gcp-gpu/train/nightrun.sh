#!/usr/bin/env bash
# Runs ON the serving GPU box (prapthi-gpu) as root, in the night window when the
# site has had no generation traffic (21:00-02:00 UTC, 2:30-7:30 IST). Frees the L4
# by pausing the model services, trains one voice, renders and scores the A/B set,
# then ALWAYS brings the services back: svara first, so vLLM sizes its cache on an
# empty card, then the others (their after-svara drop-ins wait for it anyway).
#
#   nightrun.sh SPEAKER AUDIO|prepared|trained LANG [MODEL] [EPOCHS] [BATCH]
#       `trained`: no training, only render + score the existing checkpoints.
#       MODEL 1.7b (default) or 0.6b. The 1.7B wants 24 GB at batch 2; the L4 has 23,
#       so batch 1. If 1.7B runs out of memory, rerun with 0.6b.
#
# While paused: svara voices, the Sanskrit chant and songs/SFX fail on the site;
# IndicF5 voices fall back to the CPU copy on prapthi-1. Hard cap: 3 hours.
set -uo pipefail
SPK="${1:?speaker}"; SRC="${2:?audio}"; LANG_="${3:?asr language}"
MODEL="${4:-1.7b}"; EPOCHS="${5:-5}"; BATCH="${6:-1}"
U=ubuntu; H=/home/$U; T=$H/train; OUT=$H/ab/$SPK
STATUS=$H/train-$SPK.status
exec >>"$H/train-$SPK.log" 2>&1
log() { echo "[$(date -u +%H:%M:%S)] $*"; echo "$*" > "$STATUS"; }
as_u() { sudo -u $U -H "$@"; }
gpu_used() { nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | head -1; }
up() { curl -sf -m3 "http://127.0.0.1:$1/health" >/dev/null; }
if5_loaded() { curl -s -m3 http://127.0.0.1:8004/health | grep -q '"loaded": true'; }
gpu_empty() { [ "$(gpu_used)" -lt 1000 ]; }
wait_for() { local n=$1; shift; for _ in $(seq "$n"); do "$@" && return 0; sleep 5; done; return 1; }

restore() {
    local rc=$?
    log "restoring services (run exit $rc)"
    systemctl stop if5 2>/dev/null
    docker start svara-tts-api >/dev/null
    wait_for 120 up 8080 || log "WARN svara not healthy after 10 min"
    systemctl start if5 vagdhenu acedemand
    wait_for 120 if5_loaded || log "WARN IndicF5 not loaded after 10 min"
    wait_for 60 up 8006 || log "WARN chant not healthy"
    wait_for 60 up 8003 || log "WARN songs not healthy"
    local bad=""
    for p in 8080 8004 8006 8003; do up $p || bad="$bad $p"; done
    if [ -z "$bad" ]; then log "RESTORED all four engines (GPU $(gpu_used) MiB). training exit $rc"
    else log "RESTORE PROBLEM: not healthy on ports$bad. training exit $rc"; fi
}

log "start: $SPK ($LANG_, model $MODEL, $EPOCHS epochs, batch $BATCH)"
[ -f "$H/.SETUP_DONE" ] || { log "ABORT: run setup first"; exit 1; }
if [ "$SRC" = trained ]; then
    ls -d "$H/vcl/outputs/checkpoints/$SPK"/checkpoint-* >/dev/null 2>&1 || { log "ABORT: no checkpoints for $SPK"; exit 1; }
elif [ "$SRC" = prepared ]; then
    [ -f "$H/vcl/data/voices/$SPK/transcripts/transcripts.jsonl" ] || { log "ABORT: nothing prepared for $SPK"; exit 1; }
else
    [ -f "$SRC" ] || { log "ABORT: no recording at $SRC"; exit 1; }
fi
trap restore EXIT

log "pausing model services"
# `always` (not unless-stopped): if the box reboots mid-run, svara still comes back.
docker update --restart=always svara-tts-api >/dev/null
systemctl stop acedemand vagdhenu if5
docker stop -t 30 svara-tts-api >/dev/null
wait_for 24 gpu_empty || { log "ABORT: GPU still holds $(gpu_used) MiB"; exit 1; }

log "training"
timeout 150m sudo -u "$U" -H bash "$T/train_voice.sh" "$SPK" "$SRC" "$LANG_" "$EPOCHS" "$BATCH" "$MODEL"
rc=$?
[ $rc -eq 0 ] || { log "training failed (exit $rc); see the log"; exit $rc; }

# Today's clone on the same reference: IndicF5 alone on the card, then score
# everything while nothing else needs the memory.
log "baseline + scoring"
systemctl start if5
wait_for 120 if5_loaded || { log "IndicF5 did not load for the baseline"; exit 1; }
as_u python3 "$T/baseline_if5.py" "$OUT" "$T/sentences.json"
as_u bash -c "cd $H/vcl && . .venv/bin/activate && python $T/ab_tools.py score $OUT $T/sentences.json"
touch "$OUT/.DONE"
log "done; report at $OUT/report.md"
