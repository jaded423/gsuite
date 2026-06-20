#!/usr/bin/env bash
# enable-apis.sh — enable the 7 Google APIs gsuite needs, in a given GCP project.
#
# Run once per project before creating that project's OAuth client. Requires
# gcloud auth with rights on the project.
#
# USAGE:  ./enable-apis.sh <PROJECT_ID>
#   e.g.  ./enable-apis.sh ancient-sunspot-471815-g9   # Elevated

set -euo pipefail

PROJECT="${1:-}"
[[ -n "$PROJECT" ]] || { echo "usage: $0 <PROJECT_ID>" >&2; exit 64; }

APIS=(
  gmail.googleapis.com
  drive.googleapis.com
  docs.googleapis.com
  sheets.googleapis.com
  slides.googleapis.com
  calendar-json.googleapis.com
  tasks.googleapis.com
)

echo "Enabling ${#APIS[@]} APIs on project: $PROJECT"
gcloud services enable "${APIS[@]}" --project="$PROJECT"
echo "✓ done. Verify: gcloud services list --enabled --project=$PROJECT"
