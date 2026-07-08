#!/usr/bin/env bash
# setup-org-clients.sh — install a DISTINCT OAuth client per account config dir.
#
# This supersedes the single-client model in remint-oauth.sh. Under the
# multi-org architecture each account authenticates against its OWN GCP project:
#
#   elevated  → Internal app in the Elevated Workspace GCP project
#   point4    → Internal app in the Point4 Workspace GCP project
#   jaded     → External app (publishing status: Testing) in danger-zone-007
#               (consumer Gmail can't be Internal — no Workspace org)
#
# Internal apps need NO verification, NO demo video, NO CASA assessment, have NO
# 100-user cap, and their refresh tokens DON'T expire after 7 days. Restricted
# Gmail scopes (gmail.modify, gmail.settings.basic) are allowed Internal.
#
# Each client must be a Desktop (installed) OAuth client — that's the flow this
# CLI uses. Create one per project in:
#   APIs & Services → Credentials → Create credentials → OAuth client ID
#   → Application type: Desktop app
# and enable the 7 APIs first (see enable-apis.sh).
#
# USAGE:
#   ./setup-org-clients.sh elevated=~/Downloads/el.json \
#                          point4=~/Downloads/p4.json jaded=~/Downloads/jaded.json
#   (any subset of accounts; omit the ones you're not changing)
#
# Re-running is safe: each install is re-validated and the prior client is
# backed up to <dir>/backups/ first.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GSUITE_BIN="$REPO_DIR/.venv/bin/gsuite"
STAMP="$(date +%Y%m%d-%H%M%S)"

declare -A DIR_FOR=(
  [elevated]="$HOME/.config/gsuite-elevated"
  [point4]="$HOME/.config/gsuite-point4"
  [jaded]="$HOME/.config/gsuite-jaded"
)

if [[ $# -eq 0 ]]; then
  echo "usage: $0 <account>=<client.json> [<account>=<client.json> ...]" >&2
  echo "accounts: elevated point4 jaded" >&2
  exit 64
fi

if [[ ! -x "$GSUITE_BIN" ]]; then
  echo "refusing: gsuite entrypoint not found at $GSUITE_BIN (build the venv first)" >&2
  exit 1
fi

# Parse + validate every pair BEFORE touching anything.
declare -A PATH_FOR
for pair in "$@"; do
  acct="${pair%%=*}"; cpath="${pair#*=}"
  [[ "$acct" == "$pair" ]] && { echo "bad arg (need account=path): $pair" >&2; exit 64; }
  [[ -n "${DIR_FOR[$acct]:-}" ]] || { echo "unknown account: $acct" >&2; exit 64; }
  [[ -f "$cpath" ]] || { echo "no such file for $acct: $cpath" >&2; exit 64; }
  [[ -d "${DIR_FOR[$acct]}" ]] || { echo "no config dir for $acct: ${DIR_FOR[$acct]}" >&2; exit 64; }

  proj="$(python3 -c '
import json, sys
c = json.load(open(sys.argv[1]))
key = next(iter(c))
if key != "installed":
    sys.exit("not a Desktop (installed) OAuth client: top-level key is %r (got %r)" % (key, list(c)))
print(c[key].get("project_id", "?"))
' "$cpath")"
  echo "✓ $acct: valid Desktop client (project: $proj)"
  PATH_FOR[$acct]="$cpath"
done

# Install + reauth each.
for acct in "${!PATH_FOR[@]}"; do
  dir="${DIR_FOR[$acct]}"
  mkdir -p "$dir/backups"
  if [[ -f "$dir/oauth-client.json" ]]; then
    cp -p "$dir/oauth-client.json" "$dir/backups/oauth-client.json.bak-$STAMP"
    echo "  backed up $acct/oauth-client.json -> backups/oauth-client.json.bak-$STAMP"
  fi
  # New client → old tokens are invalid; archive so a stale token can't mask a failure.
  if [[ -f "$dir/tokens.json" ]]; then
    mv "$dir/tokens.json" "$dir/backups/tokens.json.bak-$STAMP"
  fi
  install -m 600 "${PATH_FOR[$acct]}" "$dir/oauth-client.json"
  echo "✓ installed new client into $acct"
done

echo
echo "Re-authorizing. A browser opens per account — pick the MATCHING Google account."
for acct in "${!PATH_FOR[@]}"; do
  dir="${DIR_FOR[$acct]}"
  echo
  read -r -p "Re-auth $acct now? [Y/n] " ans
  case "${ans:-Y}" in
    [nN]*) echo "  skipped — run later: GSUITE_CONFIG_DIR=$dir $GSUITE_BIN auth" ;;
    *)     GSUITE_CONFIG_DIR="$dir" "$GSUITE_BIN" auth ;;
  esac
done

echo
echo "Done. Verify with: ./check-oauth.sh"
