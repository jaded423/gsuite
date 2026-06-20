#!/usr/bin/env bash
# remint-oauth.sh — swap the gsuite OAuth client across all 4 account config dirs
# and re-authorize each account.
#
# WHY: the original OAuth client lived in the Elevated GCP project
# (ancient-sunspot-471815-g9). It was reminted into the personal `danger-zone-007`
# project so gsuite no longer depends on company infrastructure. This script does
# the mechanical, repeatable half; the GCP-console half is manual (see USAGE).
#
# USAGE:
#   1. (Manual, browser) In Google Cloud console, project `danger-zone-007`:
#        APIs & Services → Credentials → Create credentials → OAuth client ID
#        → Application type: Desktop app → name it (e.g. "gsuite-desktop").
#        The consent screen already exists (shared with the n8n client). Download
#        the client JSON.
#   2. Run:  ./remint-oauth.sh ~/Downloads/client_secret_xxx.json
#        → validates it's a danger-zone-007 desktop client, backs up each dir's
#          current oauth-client.json, installs the new one in all 4 dirs, then
#          drives the browser re-auth for each account in turn.
#   3. (Manual, browser) Re-add Cody as a test user on the danger-zone-007 OAuth
#        app (his Elevated-project test-user grant does NOT carry over).
#
# Re-running is safe: it re-validates and re-backs-up before each swap.

set -euo pipefail

EXPECTED_PROJECT="danger-zone-007"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GSUITE_BIN="$REPO_DIR/.venv/bin/gsuite"
STAMP="$(date +%Y%m%d-%H%M%S)"

# account label -> config dir
CONFIG_DIRS=(
  "$HOME/.config/gsuite-elevated"  # elevated
  "$HOME/.config/gsuite-dax"     # dax
  "$HOME/.config/gsuite-jaded"   # jaded
  "$HOME/.config/gsuite-point4"  # point4
)

NEW_CLIENT="${1:-}"
if [[ -z "$NEW_CLIENT" || ! -f "$NEW_CLIENT" ]]; then
  echo "usage: $0 <path-to-new-oauth-client.json>" >&2
  exit 64
fi

# --- validate the downloaded client before touching anything ---------------
project_id="$(python3 -c '
import json, sys
c = json.load(open(sys.argv[1]))
key = next(iter(c))                       # "installed" for a Desktop client
if key != "installed":
    sys.exit("not a Desktop (installed) OAuth client: top-level key is %r" % key)
print(c[key].get("project_id", ""))
' "$NEW_CLIENT")"

if [[ "$project_id" != "$EXPECTED_PROJECT" ]]; then
  echo "refusing: client project_id is '$project_id', expected '$EXPECTED_PROJECT'" >&2
  echo "(make sure you created the client in the $EXPECTED_PROJECT GCP project)" >&2
  exit 1
fi
echo "✓ validated Desktop OAuth client for project $project_id"

if [[ ! -x "$GSUITE_BIN" ]]; then
  echo "refusing: gsuite entrypoint not found at $GSUITE_BIN (build the venv first)" >&2
  exit 1
fi

# --- backup + install into each dir ----------------------------------------
for dir in "${CONFIG_DIRS[@]}"; do
  if [[ ! -d "$dir" ]]; then
    echo "skip (no dir): $dir"
    continue
  fi
  mkdir -p "$dir/backups"
  if [[ -f "$dir/oauth-client.json" ]]; then
    cp -p "$dir/oauth-client.json" "$dir/backups/oauth-client.json.bak-$STAMP"
    echo "  backed up $(basename "$dir")/oauth-client.json -> backups/oauth-client.json.bak-$STAMP"
  fi
  install -m 600 "$NEW_CLIENT" "$dir/oauth-client.json"
  echo "✓ installed new client into $(basename "$dir")"
done

# --- re-auth each account (interactive browser) ----------------------------
echo
echo "Now re-authorizing each account. A browser window opens per account;"
echo "pick the matching Google account and grant the scopes."
for dir in "${CONFIG_DIRS[@]}"; do
  [[ -d "$dir" ]] || continue
  echo
  read -r -p "Re-auth $(basename "$dir") now? [Y/n] " ans
  case "${ans:-Y}" in
    [nN]*) echo "  skipped — run later: GSUITE_CONFIG_DIR=$dir $GSUITE_BIN auth" ;;
    *)     GSUITE_CONFIG_DIR="$dir" "$GSUITE_BIN" auth ;;
  esac
done

echo
echo "Done. Remaining manual step: re-add Cody as a test user on the"
echo "$EXPECTED_PROJECT OAuth consent screen. Then delete the old client in the"
echo "Elevated project (ancient-sunspot-471815-g9) once all 4 accounts work."
