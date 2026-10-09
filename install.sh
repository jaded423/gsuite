#!/usr/bin/env sh
# Install gsuite on this machine: venv + editable install + register the live
# per-account instances at user scope. Idempotent. Tokens live in
# ~/.config/gsuite/ (bare = j@jadedviber.com) and ~/.config/gsuite-{jaded,brown}/
# (not created here — copy an existing config dir, or run add-account.sh).
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip -q install -e .
BIN="$DIR/.venv/bin/gsuite"

# bare instance: default config dir, no GSUITE_CONFIG_DIR
claude mcp remove gsuite -s user >/dev/null 2>&1 || true
claude mcp add gsuite -s user -- "$BIN" serve

for label in jaded brown; do
  claude mcp remove "gsuite-$label" -s user >/dev/null 2>&1 || true
  claude mcp add "gsuite-$label" -s user -e GSUITE_CONFIG_DIR="$HOME/.config/gsuite-$label" -- "$BIN" serve
done
echo "gsuite: 3 instances registered (gsuite, gsuite-jaded, gsuite-brown)."
echo "Re-auth an expired account:  GSUITE_CONFIG_DIR=~/.config/gsuite-<acct> $BIN auth --expect <email>"
