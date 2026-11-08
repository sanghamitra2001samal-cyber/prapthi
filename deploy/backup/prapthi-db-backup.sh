#!/bin/bash
# Nightly dump of the only user database (accounts, plans, payments).
# Added 8 Nov 2026: until then there was no backup of any kind.
#  1. a local copy, kept 14 days, in /var/backups/prapthi-db
#  2. an encrypted copy sent to the GPU server, which belongs to a separate
#     Google account, so losing this server or its project loses neither.
#     It is encrypted to a public key; the private key exists only on the
#     owner's Mac (~/.config/prapthi-backup), so the GPU server cannot read it.
set -euo pipefail
DB=ayaanvoice
DIR=/var/backups/prapthi-db
KEEP_DAYS=14
CONF=/etc/prapthi-backup
install -d -m 700 "$DIR"
out="$DIR/$DB-$(date -u +%Y%m%d-%H%M%S).dump"
sudo -u postgres pg_dump -Fc "$DB" > "$out.tmp"
pg_restore -l "$out.tmp" > /dev/null          # must be a readable archive
mv "$out.tmp" "$out"; chmod 600 "$out"
find "$DIR" -name "$DB-*.dump" -mtime +"$KEEP_DAYS" -delete
echo "local copy: $out ($(stat -c %s "$out") bytes)"

# Off-server copy: a random AES key per night, itself encrypted with RSA-OAEP.
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
K=$(openssl rand -hex 32)
printf %s "$K" | openssl pkeyutl -encrypt -pubin -inkey "$CONF/backup-pub.pem" \
    -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256 -out "$T/key.enc"
K="$K" openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:K -in "$out" -out "$T/data.enc"
unset K
sha256sum "$out" | cut -d' ' -f1 > "$T/sha256"
if tar -C "$T" -cf - key.enc data.enc sha256 | ssh -i /root/.ssh/prapthi_dbdrop \
        -o UserKnownHostsFile="$CONF/known_hosts" -o StrictHostKeyChecking=yes \
        -o BatchMode=yes -o ConnectTimeout=30 dbdrop@35.244.48.2 store; then
    echo "off-server copy sent ($(cat "$T/sha256" | cut -c1-16))"
else
    echo "OFF-SERVER COPY FAILED (the local copy is fine)" >&2
    exit 1
fi
