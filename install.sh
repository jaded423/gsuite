#!/usr/bin/env sh
# Install gsuite on this machine: venv + editable install + register the 4
# per-account instances at user scope. Idempotent. Tokens live in
# ~/.config/gsuite-{elevated,jaded,point4}/ (not created here — run `gsuite auth`
# per account, or copy an existing config dir).
set -e
DIR=$(cd "$(dirname "$0")" && pwd)
cd "$DIR"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip -q install -e .
BIN="$DIR/.venv/bin/gsuite"
for pair in elevated:gsuite-elevated jaded:gsuite-jaded point4:gsuite-point4; do
  label=${pair%%:*}; cfg=${pair##*:}
  claude mcp remove "gsuite-$label" -s user >/dev/null 2>&1 || true
  claude mcp add "gsuite-$label" -s user -e GSUITE_CONFIG_DIR="$HOME/.config/$cfg" -- "$BIN" serve
done
echo "gsuite: 4 instances registered."
echo "Re-auth an expired account:  GSUITE_CONFIG_DIR=~/.config/gsuite-<acct> $BIN auth"
