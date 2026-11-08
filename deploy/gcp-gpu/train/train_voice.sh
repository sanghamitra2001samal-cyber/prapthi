#!/usr/bin/env bash
# Runs ON the training VM as ubuntu (trainbox starts it inside tmux). Turns one
# recording into a fine-tuned Qwen3-TTS voice, then renders the A/B test set.
#
#   train_voice.sh SPEAKER AUDIO_FILE|prepared|trained ASR_LANG [EPOCHS] [BATCH] [MODEL]
#
# `prepared` skips the recording pipeline and trains on clips already in
# data/voices/SPEAKER (see prep_syspin.py). `trained` skips training altogether and
# only renders the A/B set from the checkpoints already in outputs/checkpoints/SPEAKER.
#
# MODEL is 1.7b (default) or 0.6b, the smaller base for cards under 24 GB.
#
# ASR_LANG is the Whisper language of the recording (hi, en, te, ...). Whisper
# transcripts are only trustworthy for Hindi and English; for other languages
# proofread data/voices/SPEAKER/transcripts before trusting the result.
set -euo pipefail
SPK="${1:?speaker}"; SRC="${2:?audio file}"; LANG_="${3:?asr language}"
EPOCHS="${4:-5}"; BATCH="${5:-8}"   # 8 fits the full 96 GB card; 2 on 24 GB, 1 on the 23 GB L4
MODEL="${6:-1.7b}"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd ~/vcl && . .venv/bin/activate
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# The stock config transcribes as English; a per-voice copy carries the real language.
CONF="config/$SPK.yaml"
sed -E "s/^(  language: )en\$/\1$LANG_/" config/default.yaml > "$CONF"
grep -q "^  language: $LANG_\$" "$CONF" || { echo "could not set asr.language in $CONF"; exit 1; }
case "$MODEL" in
    1.7b) ;;
    0.6b) sed -i -E "s/^(  init_model_(path|id): .*Qwen3-TTS-12Hz-)1\.7B-Base\$/\10.6B-Base/" "$CONF"
          [ "$(grep -c '12Hz-0.6B-Base$' "$CONF")" = 2 ] || { echo "could not switch $CONF to 0.6B"; exit 1; } ;;
    *) echo "MODEL must be 1.7b or 0.6b"; exit 1 ;;
esac
V=(--speaker "$SPK" --config "$CONF")
[ "$MODEL" = 1.7b ] || vcl setup --download "${V[@]}"     # fetch the 0.6B base once

if [ "$SRC" = trained ]; then
    ls -d "outputs/checkpoints/$SPK"/checkpoint-* >/dev/null || { echo "no checkpoints for $SPK"; exit 1; }
    log "render only: using the existing checkpoints of $SPK"
elif [ "$SRC" = prepared ]; then
    # Clips and checked transcripts already in data/voices/$SPK (prep_syspin.py).
    log "using prepared clips in data/voices/$SPK"
    vcl dataset "${V[@]}" --min-minutes 5 --force
else
    log "data pipeline: $SRC (asr language $LANG_)"
    vcl run "${V[@]}" --input "$SRC" --min-minutes 5 --force
fi
if [ "$SRC" != trained ]; then
    cat "data/voices/$SPK/dataset/dataset_stats.json"; echo
    log "prepare + train ($EPOCHS epochs, batch $BATCH)"
    vcl prepare "${V[@]}" --force
    vcl train "${V[@]}" --epochs "$EPOCHS" --batch-size "$BATCH" --force
fi
ls -d "outputs/checkpoints/$SPK"/checkpoint-*

OUT=~/ab/"$SPK"
log "A/B render -> $OUT"
python "$HERE/ab_tools.py" reference "$SPK" "$OUT"
python "$HERE/ab_tools.py" generate "$SPK" "$HERE/sentences.json" "$OUT"
touch "$OUT/.TRAIN_DONE"
log "done. Next: trainbox baseline $SPK, then trainbox score $SPK"
