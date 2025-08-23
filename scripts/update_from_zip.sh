#!/usr/bin/env bash
set -euo pipefail
ZIP="$1"
WORKDIR="/opt/farmcare"
TMP="/tmp/farmcare_update"
mkdir -p "$TMP"
unzip -o "$ZIP" -d "$TMP"
rsync -a --delete "$TMP"/ "$WORKDIR"/
systemctl restart farmcare.service
echo "OK"
