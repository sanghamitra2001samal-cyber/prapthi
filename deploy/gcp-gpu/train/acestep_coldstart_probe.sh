#!/usr/bin/env bash
# Runs ON the serving GPU box as root, in the night window. Measures where a cold
# song start spends its time: one SFX request through acedemand from a dropped page
# cache, with vmstat sampled every second (si/so = swap traffic, bi = disk reads,
# wa = waiting on disk, us/sy = CPU). Waits for any training run to finish first.
#
#   acestep_coldstart_probe.sh [OUT_DIR]
set -uo pipefail
OUT="${1:-/home/ubuntu/probe-$(date -u +%Y%m%d)}"
mkdir -p "$OUT"; exec >>"$OUT/probe.log" 2>&1
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

for i in $(seq 360); do
    systemctl list-units --no-legend 'prapthi-train-*.service' | grep -q running || break
    sleep 30
done
for i in $(seq 120); do curl -s -m3 http://127.0.0.1:8004/health | grep -q '"loaded": true' && break; sleep 5; done
curl -sf -m3 http://127.0.0.1:8003/health >/dev/null || { log "ABORT: acedemand not healthy"; exit 1; }

free -m > "$OUT/free-before.txt"
for p in /proc/[0-9]*; do s=$(awk '/VmSwap/{print $2}' $p/status 2>/dev/null)
    [ "${s:-0}" -gt 100000 ] && echo "$((s/1024)) MB $(tr '\0' ' ' < $p/cmdline | cut -c1-80)"; done | sort -rn > "$OUT/swap-before.txt"

sync; echo 1 > /proc/sys/vm/drop_caches          # the state a song meets after a long idle
vmstat -n -t 1 > "$OUT/vmstat.txt" & VM=$!
log "cold SFX request"
t0=$(date +%s.%N)
code=$(curl -s -m600 -o "$OUT/sfx.wav" -w '%{http_code}' -H 'Content-Type: application/json' \
    -d '{"prompt": "rain on a tin roof", "duration": 4}' http://127.0.0.1:8003/sfx)
t1=$(date +%s.%N)
log "cold SFX: HTTP $code in $(awk "BEGIN{printf \"%.1f\", $t1 - $t0}") s"
sleep 5; kill $VM
journalctl -u acedemand -u acestep --since "-15 min" --no-pager -o short-precise \
    | grep -vE "GET /health|blob data" > "$OUT/journal.txt"
free -m > "$OUT/free-after.txt"
awk 'NR>2 {si+=$7; so+=$8; bi+=$9; n++; if ($16>wa) wa=$16} END {
    printf "samples %d s | swap-in %.0f MB | swap-out %.0f MB | disk read %.0f MB | peak io-wait %d%%\n",
    n, si/1024, so/1024, bi/1024, wa}' "$OUT/vmstat.txt" | tee "$OUT/summary.txt"
log "probe done -> $OUT"
