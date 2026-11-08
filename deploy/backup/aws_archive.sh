#!/usr/bin/env bash
# Copies the AWS GPU disks to Google Drive, encrypted, without touching them.
#
#   aws_archive.sh setup      make the encryption passphrases (local only)
#   aws_archive.sh signin     you sign in to Google Drive in your browser
#   aws_archive.sh preflight  read-only checks: right account, space, AWS access
#   aws_archive.sh start      snapshot, build the temporary machine, start copying
#   aws_archive.sh status     progress of the copy
#   aws_archive.sh cleanup    delete the temporary machine and its disks
#
# The live server is never logged in to and its disks are never attached: the
# temporary machine reads new volumes made from snapshots. See README.md.
set -euo pipefail

ACCOUNT="hudsundm@gmail.com"      # refuses to upload to any other Google account
REGION="ap-south-1"
AZ="ap-south-1a"
SUBNET="subnet-07247550777f92f87"
VPC="vpc-0a7159778599a8c21"
KEY_NAME="prapthi-gpu"
KEY_FILE="$HOME/.ssh/prapthi-gpu.pem"
IMAGE="ami-0fc5120b2d80d4749"     # Ubuntu 24.04
TYPES="m6i.large m6a.large m5.large m5a.large r6i.large r5.large t3.large"  # first with free capacity
TYPE="${TYPES%% *}"
SCRATCH_GB=600                   # both disks hold at most 400 GB before compression
ORIGINALS="vol-045f7905aea5ec844 vol-0cd9a418d4027d033"
TAG="prapthi-aws-archive"
SELF_DESTRUCT_MIN=4320            # a forgotten machine must not become a surprise bill

HOME_DIR="$HOME/.config/prapthi-archive"
RC="$HOME_DIR/rclone.conf"
PASS="$HOME_DIR/PASSPHRASES-keep-these-safe.txt"
STATE="$HOME_DIR/state.env"
HERE="$(cd "$(dirname "$0")" && pwd)"
SSH_KNOWN="$HOME_DIR/known_hosts"

aws_() { aws --region "$REGION" --output text "$@"; }
say() { echo "== $*"; }
die() { echo "STOPPED: $*" >&2; exit 1; }
remember() { echo "$1=$2" >> "$STATE"; }
tags() { echo "ResourceType=$1,Tags=[{Key=Purpose,Value=$TAG}]"; }

load() { if [ -f "$STATE" ]; then . "$STATE"; fi; }

setup() {
    mkdir -p "$HOME_DIR"; chmod 700 "$HOME_DIR"
    [ -f "$PASS" ] && { say "passphrases already exist, keeping them"; return; }
    local p1 p2
    p1=$(openssl rand -base64 36 | tr -d '\n'); p2=$(openssl rand -base64 36 | tr -d '\n')
    ( umask 077; printf 'password=%s\npassword2=%s\n' "$p1" "$p2" > "$PASS" )
    rclone config create archive crypt remote=archive-drive:prapthi-aws-archive \
        password="$p1" password2="$p2" --obscure --non-interactive --no-output --config "$RC" >/dev/null
    chmod 600 "$RC"
    say "passphrases saved in $PASS"
}

signin() {
    [ -f "$RC" ] || setup
    say "Your browser will open. Choose $ACCOUNT and click Allow."
    # A sign-in that failed halfway leaves a section with no token behind.
    rclone config delete archive-drive --config "$RC" 2>/dev/null || true
    # drive.file: rclone can see only the files it created, nothing else in Drive.
    rclone config create archive-drive drive scope=drive.file --config "$RC" --no-output
    chmod 600 "$RC"
    drive_account
}

# Prints the email and free space of the signed-in Drive; the token is never shown.
drive_account() {
    rclone about archive-drive: --config "$RC" >/dev/null
    RC="$RC" python3 - <<'PY'
import configparser, json, os, urllib.request
c = configparser.RawConfigParser(); c.read(os.environ["RC"])
tok = json.loads(c["archive-drive"]["token"])["access_token"]
r = urllib.request.Request("https://www.googleapis.com/drive/v3/about?fields=user(emailAddress),storageQuota",
                           headers={"Authorization": "Bearer " + tok})
a = json.load(urllib.request.urlopen(r, timeout=20)); q = a["storageQuota"]
gb = lambda k: int(q.get(k, 0)) / 1e9
print("account", a["user"]["emailAddress"])
print("total_gb %.0f" % gb("limit"))
print("free_gb %.0f" % (gb("limit") - gb("usage")))
PY
}

preflight() {
    [ -f "$PASS" ] || die "run setup first"
    grep -q 'archive-drive' "$RC" || die "run signin first"
    local info who free
    info=$(drive_account); echo "$info"
    who=$(echo "$info" | awk '/^account/{print $2}'); free=$(echo "$info" | awk '/^free_gb/{print $2}')
    [ "$who" = "$ACCOUNT" ] || die "signed in as $who, expected $ACCOUNT"
    [ "$free" -gt 450 ] || die "only $free GB free on Drive"
    say "test file: encrypt, upload, read back, delete"
    local t="preflight-$$"
    echo "prapthi archive test" | rclone rcat "archive:$t" --config "$RC"
    [ "$(rclone cat "archive:$t" --config "$RC")" = "prapthi archive test" ] || die "test file came back different"
    rclone deletefile "archive:$t" --config "$RC"
    say "AWS permissions (nothing is created)"
    local c out
    for c in "create-snapshot --volume-id ${ORIGINALS%% *}" \
             "run-instances --image-id $IMAGE --instance-type $TYPE --subnet-id $SUBNET"; do
        # A dry run that would succeed still exits non-zero, with DryRunOperation.
        # shellcheck disable=SC2086
        out=$(aws --region "$REGION" ec2 $c --dry-run 2>&1 || true)
        case "$out" in *DryRunOperation*) ;; *) echo "$out" >&2; die "AWS refuses: $c" ;; esac
    done
    [ -r "$KEY_FILE" ] || die "missing $KEY_FILE"
    say "ready"
}

snapshot_all() {
    local v var id
    for v in $ORIGINALS; do
        var="SNAP_$(echo "$v" | tr -d '-')"
        if [ -z "${!var:-}" ]; then
            id=$(aws_ ec2 create-snapshot --volume-id "$v" --description "$TAG copy of $v" \
                 --tag-specifications "$(tags snapshot)" --query SnapshotId)
            remember "$var" "$id"; eval "$var=$id"
            say "snapshot $id of $v"
        fi
    done
    for v in $ORIGINALS; do
        var="SNAP_$(echo "$v" | tr -d '-')"
        while :; do
            local s; s=$(aws_ ec2 describe-snapshots --snapshot-ids "${!var}" --query 'Snapshots[0].[State,Progress]')
            case "$s" in completed*) break ;; error*) die "snapshot ${!var} failed" ;; esac
            echo "   ${!var}: $s"; sleep 30
        done
    done
}

# Home internet addresses change, so the firewall rule follows this Mac.
allow_this_mac() {
    local ip old; ip=$(curl -s https://checkip.amazonaws.com)
    aws_ ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr "$ip/32" >/dev/null 2>&1 || true
    for old in $(aws_ ec2 describe-security-groups --group-ids "$SG" --query 'SecurityGroups[0].IpPermissions[0].IpRanges[].CidrIp'); do
        [ "$old" = "$ip/32" ] || aws_ ec2 revoke-security-group-ingress --group-id "$SG" --protocol tcp --port 22 --cidr "$old" >/dev/null 2>&1 || true
    done
}

build_machine() {
    load
    if [ -z "${SG:-}" ]; then
        SG=$(aws_ ec2 create-security-group --group-name "$TAG-$(date +%s)" --description "$TAG temporary" \
             --vpc-id "$VPC" --tag-specifications "$(tags security-group)" --query GroupId)
        remember SG "$SG"
    fi
    allow_this_mac

    if [ -z "${HELPER:-}" ]; then
        # Shutting down terminates it, and every volume on it is deleted with it.
        local t
        for t in $TYPES; do
            say "trying $t"
            HELPER=$(aws_ ec2 run-instances --image-id "$IMAGE" --instance-type "$t" --subnet-id "$SUBNET" \
                --key-name "$KEY_NAME" --security-group-ids "$SG" --associate-public-ip-address \
                --instance-initiated-shutdown-behavior terminate \
                --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3,DeleteOnTermination=true}" \
                "DeviceName=/dev/sdb,Ebs={VolumeSize=$SCRATCH_GB,VolumeType=gp3,Throughput=500,Iops=6000,DeleteOnTermination=true}" \
                --tag-specifications "$(tags instance)" "$(tags volume)" --query 'Instances[0].InstanceId') && break
            HELPER=""
        done
        [ -n "$HELPER" ] || die "AWS has none of these machine types free right now: $TYPES"
        remember HELPER "$HELPER"
    fi
    say "temporary machine $HELPER"
    aws --region "$REGION" ec2 wait instance-running --instance-ids "$HELPER"

    local v var src dev="f" name="" vol
    for v in $ORIGINALS; do
        case "$v" in vol-045f7905aea5ec844) name=live ;; *) name=old ;; esac
        var="COPY_$name"
        if [ -z "${!var:-}" ]; then
            src="SNAP_$(echo "$v" | tr -d '-')"
            vol=$(aws_ ec2 create-volume --availability-zone "$AZ" --snapshot-id "${!src}" --volume-type gp3 \
                  --tag-specifications "$(tags volume)" --query VolumeId)
            aws --region "$REGION" ec2 wait volume-available --volume-ids "$vol"
            aws --region "$REGION" ec2 attach-volume --volume-id "$vol" --instance-id "$HELPER" --device "/dev/sd$dev" >/dev/null
            aws --region "$REGION" ec2 wait volume-in-use --volume-ids "$vol"
            aws --region "$REGION" ec2 modify-instance-attribute --instance-id "$HELPER" \
                --block-device-mappings "DeviceName=/dev/sd$dev,Ebs={DeleteOnTermination=true}" >/dev/null
            remember "$var" "$vol"; eval "$var=$vol"
            say "$name copy is $vol"
        fi
        dev="g"
    done
}

helper_ip() { aws_ ec2 describe-instances --instance-ids "$HELPER" --query 'Reservations[0].Instances[0].PublicIpAddress'; }
ssh_() {
    ssh -i "$KEY_FILE" -o UserKnownHostsFile="$SSH_KNOWN" -o StrictHostKeyChecking=accept-new \
        -o ConnectTimeout=15 -o ServerAliveInterval=30 "ubuntu@$(helper_ip)" "$@"
}

inventory() {
    local d="$HOME_DIR/inventory"; mkdir -p "$d"
    aws --region "$REGION" ec2 describe-instances > "$d/instances.json"
    aws --region "$REGION" ec2 describe-volumes > "$d/volumes.json"
    aws --region "$REGION" ec2 describe-snapshots --owner-ids self > "$d/snapshots.json"
    aws --region "$REGION" ec2 describe-images --owners self > "$d/images.json"
    aws --region "$REGION" ec2 describe-security-groups > "$d/security-groups.json"
    aws --region "$REGION" ec2 describe-addresses > "$d/addresses.json"
    aws --region "$REGION" ec2 describe-key-pairs > "$d/key-pairs.json"
    aws --region "$REGION" ec2 describe-subnets > "$d/subnets.json"
    aws --region "$REGION" ec2 describe-route-tables > "$d/route-tables.json"
}

start() {
    preflight
    load
    say "snapshots (the live server keeps running)"
    snapshot_all
    build_machine
    load
    until ssh_ true 2>/dev/null; do sleep 10; done
    inventory
    say "preparing the temporary machine"
    scp -q -i "$KEY_FILE" -o UserKnownHostsFile="$SSH_KNOWN" "$RC" "$HERE/archive_worker.sh" "ubuntu@$(helper_ip):/tmp/"
    scp -q -r -i "$KEY_FILE" -o UserKnownHostsFile="$SSH_KNOWN" "$HOME_DIR/inventory" "ubuntu@$(helper_ip):/tmp/"
    ssh_ "sudo bash -s" "$COPY_live" "$COPY_old" "$SELF_DESTRUCT_MIN" <<'REMOTE'
set -euo pipefail
live="${1//-/}"; old="${2//-/}"; destruct="$3"
shutdown -P "+$destruct" "archive machine self-destruct" || true
install -m 600 /tmp/rclone.conf /root/rclone.conf; rm -f /tmp/rclone.conf
install -m 755 /tmp/archive_worker.sh /root/archive_worker.sh
cloud-init status --wait >/dev/null 2>&1 || true
for i in 1 2 3 4 5 6 7 8 9 10; do apt-get -qq -o DPkg::Lock::Timeout=300 update && break; sleep 15; done
DEBIAN_FRONTEND=noninteractive apt-get -qq -o DPkg::Lock::Timeout=300 install -y zstd acl curl >/dev/null
# The same rclone that signed in: Ubuntu's own package is years older.
rv=v1.75.2; deb="rclone-$rv-linux-amd64.deb"
(cd /tmp && curl -fsSLO "https://downloads.rclone.org/$rv/$deb" \
    && curl -fsSL "https://downloads.rclone.org/$rv/SHA256SUMS" | grep " $deb\$" | sha256sum -c --quiet \
    && dpkg -i "$deb" >/dev/null)

# The scratch disk is whichever blank disk has no partitions and is not a copy.
if ! mountpoint -q /archive; then
    blank=""
    for d in $(lsblk -dnpo NAME,TYPE | awk '$2=="disk"{print $1}'); do
        if [ "$(lsblk -no NAME "$d" | wc -l)" = 1 ] && [ -z "$(lsblk -no FSTYPE "$d" | tr -d ' ')" ]; then
            blank="$d"; break
        fi
    done
    [ -n "$blank" ] || { echo "STOPPED: no blank scratch disk found"; exit 1; }
    mkfs.ext4 -q "$blank"; mkdir -p /archive; mount "$blank" /archive
fi
mkdir -p /archive/out/aws-inventory; cp -r /tmp/inventory/. /archive/out/aws-inventory/

cat > /root/run.sh <<RUN
#!/usr/bin/env bash
set -euo pipefail
W=/root/archive_worker.sh
pack_disk() {
    local name="\$1" vol="\$2" p n fs m
    local base="/dev/disk/by-id/nvme-Amazon_Elastic_Block_Store_\$vol"
    udevadm settle
    sfdisk -d "\$base" > "/archive/out/aws-inventory/\$name.partitions.txt" || true
    for p in "\$base"-part*; do
        n="\${p##*part}"; fs=\$(blkid -o value -s TYPE "\$p" || true)
        case "\$fs" in
            ext4|vfat) ;;
            "") echo "no filesystem on \$p, nothing to copy"; continue ;;
            *) echo "STOPPED: \$p is \$fs, which this copy does not handle"; exit 1 ;;
        esac
        m="/mnt/\$name-p\$n"; mkdir -p "\$m"; mountpoint -q "\$m" || mount -o ro "\$p" "\$m"
        \$W pack "\$name-p\$n" "\$m"
    done
    # The main partition must never be missed without anyone noticing.
    [ -f "/archive/out/\$name-p1/DONE" ] || { echo "STOPPED: \$name partition 1 was not packed"; exit 1; }
}
pack_disk live "$live"
pack_disk old "$old"
\$W upload
\$W verify
touch /archive/ALL-DONE
RUN
chmod +x /root/run.sh
REMOTE
    ssh_ "sudo bash -c 'nohup /root/run.sh > /archive/run.log 2>&1 < /dev/null &'"
    say "copying now. It carries on if this Mac sleeps. Check with: $0 status"
}

status() {
    load
    [ -n "${HELPER:-}" ] || die "nothing is running"
    allow_this_mac
    ssh_ "df -h /archive | tail -1; sudo tail -n 8 /archive/run.log; pgrep -f '[/]root/run.sh' >/dev/null && echo RUNNING || echo NOT-RUNNING; [ -f /archive/ALL-DONE ] && echo ALL-DONE || true"
}

cleanup() {
    load
    [ -n "${HELPER:-}" ] || die "no temporary machine recorded"
    local id t
    t=$(aws_ ec2 describe-instances --instance-ids "$HELPER" --query "Reservations[0].Instances[0].Tags[?Key=='Purpose'].Value | [0]")
    [ "$t" = "$TAG" ] || die "$HELPER is not tagged as the archive machine, leaving it alone"
    say "terminating $HELPER"
    aws --region "$REGION" ec2 terminate-instances --instance-ids "$HELPER" >/dev/null
    aws --region "$REGION" ec2 wait instance-terminated --instance-ids "$HELPER"
    for id in ${COPY_live:-} ${COPY_old:-}; do
        case " $ORIGINALS " in *" $id "*) die "refusing to touch original disk $id" ;; esac
        aws --region "$REGION" ec2 delete-volume --volume-id "$id" 2>/dev/null || true
    done
    [ -n "${SG:-}" ] && aws --region "$REGION" ec2 delete-security-group --group-id "$SG" || true
    mv "$STATE" "$STATE.finished-$(date +%s)"
    say "temporary machine gone. Snapshots kept. The original disks were never touched."
}

case "${1:-}" in
    setup) setup ;; signin) signin ;; preflight) preflight ;;
    start) start ;; status) status ;; cleanup) cleanup ;;
    *) sed -n 2,11p "$0"; exit 2 ;;
esac
