"""Thin n8n-facing wrapper scripts (phase 8).

Each module here wraps an existing pipeline module (src/extract,
src/validate, src/suppliers, src/receivables, src/pack) behind a small
CLI that prints exactly one JSON object to stdout and uses an exit code
n8n can branch on. No pipeline logic lives here — see CLAUDE.md.
"""
