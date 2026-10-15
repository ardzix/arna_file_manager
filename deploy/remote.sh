#!/bin/sh
set -eu
set +x
PHASE="$1"
RELEASE_ID=$(cat release-id.txt)
COMMIT=$(cat release-commit.txt)
case "$RELEASE_ID" in b[0-9]*-*) ;; *) exit 1 ;; esac
case "$RELEASE_ID$COMMIT" in *[!a-z0-9-]*) exit 1 ;; esac
REMOTE="/root/arnatech-releases/storage-$RELEASE_ID"
KNOWN_HOSTS=deploy/ssh_known_hosts
test -s "$KNOWN_HOSTS"
ssh_manager() {
  ssh -i "$STORAGE_SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN_HOSTS" -o GlobalKnownHostsFile=/dev/null -o ConnectTimeout=15 root@arnatech.id "$@"
}
copy_private() {
  scp -i "$STORAGE_SSH_KEY" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="$KNOWN_HOSTS" -o GlobalKnownHostsFile=/dev/null -o ConnectTimeout=15 "$1" "root@arnatech.id:$REMOTE/$2"
}
if [ "$PHASE" = stage ]; then
  ssh_manager "umask 077; mkdir -p '$REMOTE/registry'; chmod 700 '$REMOTE' '$REMOTE/registry'"
  copy_private deploy/release.py entry.py
  copy_private storage-source.tar source.tar
  copy_private "$STORAGE_ENV_FILE" runtime.env
  copy_private "$STORAGE_PUBLIC_KEY" public.pem
  copy_private .release-private/registry.json registry/config.json
  ssh_manager "chmod 600 '$REMOTE/runtime.env' '$REMOTE/public.pem' '$REMOTE/registry/config.json'"
else
  case "$PHASE" in build|migrate|roll|verify|cleanup) ;; *) exit 1 ;; esac
  ssh_manager python3 "$REMOTE/entry.py" "$PHASE" "$COMMIT" "$RELEASE_ID"
fi
