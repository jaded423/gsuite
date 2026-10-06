#!/usr/bin/env bash
# add-account.sh — give this machine a gsuite login for one more Google account.
#
# Creates ~/.config/gsuite-<name>/ with the same OAuth client the default instance
# uses (every instance shares the one `mcps` client), switches on EXACTLY the
# features named (everything else off, so the consent screen asks for no more than
# the job needs), then runs the sign-in. The sign-in is told which account it is
# for: the chooser preselects it and a login from any other account is refused,
# not saved (`gsuite auth --expect`).
#
# USAGE:
#   ./add-account.sh <name> <email> <feature> [<feature> ...]
#   e.g.  ./add-account.sh jaded jaded423@gmail.com gmail.read
#
# On a machine with no browser, forward a port and name it:
#   ssh -t -L 8765:localhost:8765 <host> \
#     'GSUITE_AUTH_PORT=8765 ~/projects/gsuite/add-account.sh jaded jaded423@gmail.com gmail.read'
#   then open the printed URL in a browser on the machine you ssh'd from.
#
# Safe to re-run: an existing dir keeps its client, its features are reset to the
# list given, and the sign-in replaces the old login only if the right account
# signs in. Feature names: gsuite features list.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$REPO_DIR/.venv/bin"
[[ -x "$BIN_DIR/gsuite" ]] || BIN_DIR="$HOME/.venvs/gsuite/bin"   # the layout on ubuntu
[[ -x "$BIN_DIR/gsuite" ]] || { echo "refusing: no gsuite venv found (looked in $REPO_DIR/.venv and ~/.venvs/gsuite)" >&2; exit 1; }

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <name> <email> <feature> [<feature> ...]" >&2
  exit 64
fi
name="$1" email="$2"; shift 2
[[ "$name" =~ ^[a-z0-9]+$ ]] || { echo "bad name '$name': lowercase letters and digits only" >&2; exit 64; }
[[ "$email" == *@*.* ]] || { echo "bad email '$email'" >&2; exit 64; }

base="$HOME/.config/gsuite"
dir="$HOME/.config/gsuite-$name"
[[ -f "$base/oauth-client.json" ]] || { echo "refusing: the default instance has no OAuth client to share ($base)" >&2; exit 1; }

mkdir -p "$dir"
chmod 700 "$dir"
if [[ ! -f "$dir/oauth-client.json" ]]; then
  install -m 600 "$base/oauth-client.json" "$dir/oauth-client.json"
  echo "✓ $name: OAuth client installed"
else
  echo "✓ $name: OAuth client already there, kept"
fi

GSUITE_CONFIG_DIR="$dir" "$BIN_DIR/python" -c '
import sys
from gsuite.settings import FEATURE_SCOPES, load_settings, save_settings
want = set(sys.argv[1:])
unknown = want - set(FEATURE_SCOPES)
if unknown:
    sys.exit("unknown feature(s): %s (known: %s)" % (sorted(unknown), sorted(FEATURE_SCOPES)))
settings = load_settings()
for feature in settings.features:
    settings.features[feature] = feature in want
save_settings(settings)
print("✓ features on: " + ", ".join(sorted(want)))
' "$@"

echo
echo "Signing in $name. Pick $email; any other account is refused."
# stdout stays visible: with GSUITE_AUTH_PORT set, the URL to open is printed there.
GSUITE_CONFIG_DIR="$dir" "$BIN_DIR/gsuite" auth --expect "$email"
echo "✓ $name: signed in as $email"
