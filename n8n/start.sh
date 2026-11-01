#!/usr/bin/env bash
# Starts n8n locally, scoped to this repo. See docs/n8n-setup.md for
# the full walkthrough (installing n8n, Google Cloud OAuth setup,
# importing the workflows, etc).
#
# What this script does and why:
#
#   - N8N_USER_FOLDER points at n8n/data/ (gitignored) instead of the
#     default ~/.n8n, so this project's n8n database, credentials, and
#     encryption key never mix with any other n8n project on this
#     machine, and never land in git.
#   - N8N_LISTEN_ADDRESS=127.0.0.1 and N8N_HOST=localhost mean n8n's
#     web server only answers on this machine - nothing on the network
#     can reach it.
#   - NODES_EXCLUDE is set to "[]" (enable every node). n8n disables the
#     "Execute Command" node by default for security — it lets a
#     workflow run arbitrary shell commands — but the intake, receivables,
#     and month-end-pack workflows in n8n/workflows/ all use it to call
#     this repo's own scripts/ wrappers, so it has to be allowed. This
#     is safe here because: n8n is bound to localhost only (above), the
#     only commands it runs are the fixed ones hardcoded into the
#     workflow JSON files you import yourself, and nothing in this repo
#     lets an external request reach n8n in the first place.
#
# Does NOT install n8n - run `n8n --version` first; if that fails, see
# docs/n8n-setup.md's "Install n8n" section before running this script.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export N8N_USER_FOLDER="$REPO_ROOT/n8n/data"
export N8N_LISTEN_ADDRESS="127.0.0.1"
export N8N_HOST="localhost"
export N8N_PORT="${N8N_PORT:-5678}"
export NODES_EXCLUDE='[]'

# The Execute Command nodes in n8n/workflows/ cd into the repo using
# this variable before calling .venv/bin/python, so they work no
# matter what directory n8n itself happens to be started from.
export INVOICE_AUTOMATION_REPO="$REPO_ROOT"

# n8n blocks nodes from reading process env vars via $env by default.
# The intake workflow's Execute Command node reads $INVOICE_AUTOMATION_REPO
# through $env, so that access has to be allowed here.
export N8N_BLOCK_ENV_ACCESS_IN_NODE=false

mkdir -p "$N8N_USER_FOLDER"

echo "Repo root:    $REPO_ROOT"
echo "Data folder:  $N8N_USER_FOLDER"
echo "Listening on: http://127.0.0.1:${N8N_PORT} (localhost only)"
echo

exec n8n start
