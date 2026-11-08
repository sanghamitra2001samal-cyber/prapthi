# AWS copy on Google Drive

`aws_archive.sh` copies the AWS GPU disks to Google Drive, encrypted, without
logging in to the live server or attaching its disks: a temporary machine reads
new volumes made from snapshots.

```bash
deploy/backup/aws_archive.sh setup       # passphrases, kept on this Mac
deploy/backup/aws_archive.sh signin      # sign in to Drive in the browser
deploy/backup/aws_archive.sh preflight   # read-only checks plus a small test file
deploy/backup/aws_archive.sh start       # snapshots, temporary machine, copy
deploy/backup/aws_archive.sh status      # progress
deploy/backup/aws_archive.sh cleanup     # only after status says ALL-DONE
```

`start` needs this Mac awake until the snapshots finish and the copy begins.
After that the copy runs by itself. If `start` is interrupted, run it again: it
carries on from `~/.config/prapthi-archive/state.env`.

The temporary machine shuts itself down and deletes itself and its disks after
three days, so a forgotten one can't become a large bill. `cleanup` does the same
at once. Snapshots are kept, and they cost money each month until deleted.

## The passphrases

Everything on Drive is encrypted. `~/.config/prapthi-archive/PASSPHRASES-keep-these-safe.txt`
holds the only keys, and **without them the copy can't be read**. Keep a copy in a
password manager, and don't put it on the same Drive.

## What is on Drive

In the folder `prapthi-aws-archive`, with file and folder names encrypted too:

- `live-pN/` and `old-pN/`, one per disk partition: `.tar.zst.part-NNNN` files, a
  `.manifest.zst` listing every path, and `.SHA256SUMS`
- `aws-inventory/`: the AWS settings (servers, disks, firewall rules, addresses)

## Restoring

On Linux, as root, with `rclone.conf` rebuilt from the passphrases:

```bash
rclone copy archive:aws/live-p1 /restore/parts --config rclone.conf
cd /restore/parts && sha256sum -c live-p1.SHA256SUMS
mkdir -p /restore/files
cat live-p1.tar.zst.part-* | zstd -dc \
  | tar --extract --numeric-owner --sparse --xattrs --xattrs-include='*' --acls -C /restore/files
```

To rebuild `rclone.conf` on a new computer:

```bash
rclone config create archive-drive drive scope=drive.file --config rclone.conf
rclone config create archive crypt remote=archive-drive:prapthi-aws-archive \
  password='...' password2='...' --obscure --config rclone.conf
```

A new sign-in with `drive.file` can't see files made under the old sign-in, so keep
`~/.config/prapthi-archive/rclone.conf` too, or use full `drive` scope when restoring.
rclone warns that its shared Google client is being retired during 2026. If that sign-in
stops working, make your own client (https://rclone.org/drive/#making-your-own-client-id)
and use full `drive` scope. The files stay in Drive whichever client wrote them.

## What this doesn't cover

- Lambda, Secrets Manager, Parameter Store, EFS and ECR: all empty in every region on
  3 Nov 2026, so nothing was missed. Check again if any of them is used later.
- The live server's temporary disk `/opt/dlami/nvme`, which was empty on 2 Nov 2026.
- The customer database. It lives on Google Cloud, not AWS.

## Nightly database backup (since 8 Nov 2026)

The user database (`ayaanvoice` on prapthi-1) had no backup at all until then.

- `prapthi-db-backup.sh` → `/usr/local/bin/prapthi-db-backup` on prapthi-1, run
  by `prapthi-db-backup.timer` at 21:30 UTC (03:00 IST).
  1. `pg_dump -Fc` to `/var/backups/prapthi-db/`, kept 14 days.
  2. An encrypted copy (fresh AES-256 key per night, wrapped with an RSA-4096
     public key in `/etc/prapthi-backup/`) sent over SSH to the GPU server,
     which belongs to a separate Google account.
- `dbdrop-receive.sh` → `/usr/local/bin/dbdrop-receive` on the GPU server: the
  forced command of the `dbdrop` user, whose key only works from prapthi-1's
  address and can only store an upload in `/srv/dbdrop/incoming` (kept 60 days).
- The private key that opens the copies is kept off the servers, on the
  owner's machine, with the restore steps beside it. Without it the off-site
  copies cannot be read.

Restore-tested on 8 Nov 2026: row counts matched the live database exactly.
