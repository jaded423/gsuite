#!/usr/bin/env bash
# check-oauth.sh — drift/status report across the 4 gsuite account config dirs.
#
# For each account: which GCP project its OAuth client belongs to, the client
# type, whether a token exists, and the scopes that token was granted. Use it to
# confirm each account points at its OWN project (multi-org model) and that the
# granted scopes match across accounts.
#
# Optional: pass --apis to also query enabled APIs per project via gcloud
# (needs gcloud auth on each project).

set -uo pipefail

CHECK_APIS=0
[[ "${1:-}" == "--apis" ]] && CHECK_APIS=1

declare -A DIR_FOR=(
  [elevated]="$HOME/.config/gsuite-elevated"
  [dax]="$HOME/.config/gsuite-dax"
  [point4]="$HOME/.config/gsuite-point4"
  [jaded]="$HOME/.config/gsuite-jaded"
)

for acct in elevated dax point4 jaded; do
  dir="${DIR_FOR[$acct]}"
  echo "── $acct  ($dir)"
  if [[ ! -d "$dir" ]]; then echo "   (no config dir)"; echo; continue; fi

  if [[ -f "$dir/oauth-client.json" ]]; then
    python3 - "$dir/oauth-client.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
k = next(iter(c))
typ = {"installed": "Desktop", "web": "Web"}.get(k, k)
print(f"   client: {typ}  project={c[k].get('project_id','?')}  cid={c[k].get('client_id','?')[:32]}…")
PY
  else
    echo "   client: MISSING"
  fi

  if [[ -f "$dir/tokens.json" ]]; then
    python3 - "$dir/tokens.json" <<'PY'
import json, sys
t = json.load(open(sys.argv[1]))
scopes = t.get("scope", "")
scopes = scopes.split() if isinstance(scopes, str) else (scopes or [])
short = sorted(s.replace("https://www.googleapis.com/auth/", "") for s in scopes)
print(f"   token:  present  ({len(short)} scopes)")
for s in short:
    print(f"             - {s}")
PY
  else
    echo "   token:  none (run: GSUITE_CONFIG_DIR=$dir gsuite auth)"
  fi

  if [[ "$CHECK_APIS" == 1 && -f "$dir/oauth-client.json" ]]; then
    proj="$(python3 -c 'import json,sys;c=json.load(open(sys.argv[1]));print(c[next(iter(c))].get("project_id",""))' "$dir/oauth-client.json")"
    if [[ -n "$proj" ]]; then
      echo "   apis enabled on $proj:"
      gcloud services list --enabled --project="$proj" \
        --filter="config.name~(gmail|drive|docs|sheets|slides|calendar|tasks)" \
        --format="value(config.name)" 2>/dev/null | sed 's/^/             - /' \
        || echo "             (gcloud query failed — check auth)"
    fi
  fi
  echo
done
