"""Safety checks on every n8n workflow JSON file in n8n/workflows/.

Per CLAUDE.md ("nothing is ever sent automatically"), these workflows
may create Gmail drafts but must never be able to send or reply to an
email, and must never carry a real credential/secret in the committed
JSON (credentials in an n8n export are always a placeholder {id, name}
pair — the actual secret lives in n8n's own encrypted store, outside
this repo).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / "n8n" / "workflows"

# Node types that can transmit an email/message. gmail/emailSend/etc are
# fine for drafting; only specific resource+operation combinations
# below actually send something.
_SEND_OPERATIONS = {"send", "reply", "replyAll"}

# Secret-shaped strings that should never appear in a committed workflow
# export. Matches common API key/token prefixes and long opaque blobs —
# deliberately broad, since the only thing that belongs here is
# placeholder credential names and n8n expressions.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    re.compile(r"ya29\.[0-9A-Za-z\-_]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
]

# Credential object fields an n8n *export* should never carry — a real
# install stores the actual secret server-side and only ever writes
# {"id": ..., "name": ...} into the workflow JSON.
_DISALLOWED_CREDENTIAL_FIELDS = {"apiKey", "accessToken", "refreshToken", "clientSecret", "data", "privateKey"}


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS_DIR.glob("*.json"))


def _iter_nodes(workflow: dict):
    yield from workflow.get("nodes", [])


def test_at_least_one_workflow_file_exists():
    assert _workflow_files(), f"No workflow JSON files found in {WORKFLOWS_DIR}"


def test_every_workflow_file_is_valid_json():
    for path in _workflow_files():
        json.loads(path.read_text(encoding="utf-8"))  # raises on bad JSON


def test_no_workflow_node_can_send_or_reply_to_an_email():
    offending: list[str] = []
    for path in _workflow_files():
        workflow = json.loads(path.read_text(encoding="utf-8"))
        for node in _iter_nodes(workflow):
            params = node.get("parameters", {})
            operation = params.get("operation")
            if operation in _SEND_OPERATIONS:
                offending.append(f"{path.name}: node {node.get('name')!r} has operation {operation!r}")
            node_type = node.get("type", "")
            if node_type.endswith("emailSend"):
                offending.append(f"{path.name}: node {node.get('name')!r} is an emailSend node")
    assert not offending, "Found node(s) that could send/reply instead of only drafting:\n" + "\n".join(offending)


def test_gmail_nodes_only_ever_create_drafts():
    for path in _workflow_files():
        workflow = json.loads(path.read_text(encoding="utf-8"))
        for node in _iter_nodes(workflow):
            if node.get("type") != "n8n-nodes-base.gmail":
                continue
            params = node.get("parameters", {})
            assert params.get("resource") == "draft", (
                f"{path.name}: Gmail node {node.get('name')!r} has resource "
                f"{params.get('resource')!r}, expected 'draft'"
            )
            assert params.get("operation") == "create", (
                f"{path.name}: Gmail node {node.get('name')!r} has operation "
                f"{params.get('operation')!r}, expected 'create'"
            )


def test_no_secret_shaped_strings_anywhere_in_the_workflow_json():
    for path in _workflow_files():
        text = path.read_text(encoding="utf-8")
        for pattern in _SECRET_PATTERNS:
            match = pattern.search(text)
            assert match is None, f"{path.name} contains a secret-shaped string: {match.group(0)[:12]}..."


def test_credentials_are_placeholders_only():
    for path in _workflow_files():
        workflow = json.loads(path.read_text(encoding="utf-8"))
        for node in _iter_nodes(workflow):
            for cred_type, cred in node.get("credentials", {}).items():
                assert isinstance(cred, dict), f"{path.name}: credential {cred_type!r} isn't a placeholder object"
                extra = _DISALLOWED_CREDENTIAL_FIELDS & cred.keys()
                assert not extra, f"{path.name}: credential {cred_type!r} carries disallowed field(s) {extra}"
                assert cred.get("id", "") == "", (
                    f"{path.name}: credential {cred_type!r} has a non-empty id — "
                    "should be a placeholder with id=''"
                )


def test_receivables_schedule_trigger_is_disabled_by_default():
    path = WORKFLOWS_DIR / "receivables.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    assert workflow.get("active") is False

    schedule_nodes = [n for n in _iter_nodes(workflow) if n.get("type") == "n8n-nodes-base.scheduleTrigger"]
    assert schedule_nodes, "Expected a Schedule Trigger node in receivables.json"
    for node in schedule_nodes:
        assert node.get("disabled") is True, f"Schedule Trigger node {node.get('name')!r} must be disabled by default"
