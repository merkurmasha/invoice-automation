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
N8N_SETUP_DOC = Path(__file__).resolve().parents[1] / "docs" / "n8n-setup.md"

# Google Sheets "append" nodes in intake.json whose columns must be
# defined manually (never auto-mapped from whatever node happens to
# feed them) and must match a documented Sheet tab 1:1. Keyed by node
# name -> the tab name as it appears in n8n-setup.md's header table.
_SHEETS_APPEND_NODES = {
    "Append to Ledger": "Ledger",
    "Append to Review queue": "Review queue",
}

# Each Sheets append node's "Drive Link" column has to build its URL from
# the *preceding* Drive "move" node's file id — that move node's own output
# has no webViewLink field, so referencing one there silently writes
# "undefined" into the cell instead of failing loudly.
_DRIVE_LINK_SOURCE_NODE = {
    "Append to Ledger": "Rename + move to processed",
    "Append to Review queue": "Move to review",
}

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


def _documented_headers(tab_name: str) -> list[str]:
    """Row 1 header list for `tab_name`, from the `| `Tab` | `Col1`, ... |`
    table in docs/n8n-setup.md — the single source of truth for what a
    Sheet tab's columns are actually called."""
    for line in N8N_SETUP_DOC.read_text(encoding="utf-8").splitlines():
        cells = re.findall(r"`([^`]+)`", line)
        if cells and cells[0] == tab_name:
            return cells[1:]
    raise AssertionError(f"No documented header row found for tab {tab_name!r} in {N8N_SETUP_DOC}")


def test_sheets_append_nodes_use_manual_mapping_matching_documented_headers():
    workflow = json.loads((WORKFLOWS_DIR / "intake.json").read_text(encoding="utf-8"))
    nodes_by_name = {n.get("name"): n for n in _iter_nodes(workflow)}

    for node_name, tab_name in _SHEETS_APPEND_NODES.items():
        node = nodes_by_name[node_name]
        assert node.get("type") == "n8n-nodes-base.googleSheets", f"{node_name} is not a Google Sheets node"

        columns = node.get("parameters", {}).get("columns", {})
        assert columns.get("mappingMode") == "defineBelow", (
            f"{node_name}: columns.mappingMode is {columns.get('mappingMode')!r}, expected 'defineBelow' "
            "(manual mapping) — automatic mapping would write whatever fields the previous node "
            "happens to output (e.g. a Drive node's id/name/mimeType) instead of the documented columns"
        )

        mapped_columns = list(columns.get("value", {}).keys())
        expected_columns = _documented_headers(tab_name)
        assert mapped_columns == expected_columns, (
            f"{node_name}: mapped columns {mapped_columns} don't match the '{tab_name}' header row "
            f"documented in {N8N_SETUP_DOC.name}: {expected_columns}"
        )

        for column, expression in columns.get("value", {}).items():
            assert "$json" not in expression, (
                f"{node_name}: column {column!r} uses the bare, context-dependent $json "
                f"({expression!r}) — this node's direct input is a Drive 'move' node, not "
                "'Parse result', so it must reference the data source by name, e.g. "
                "$('Parse result').item.json.<field>"
            )

        drive_link_expression = columns.get("value", {}).get("Drive Link", "")
        assert "webViewLink" not in drive_link_expression, (
            f"{node_name}: 'Drive Link' references webViewLink, but the Drive 'move' node's "
            f"output has no such field ({drive_link_expression!r}) — build the link from the "
            "file id instead: 'https://drive.google.com/file/d/' + ...item.json.id + '/view'"
        )
        source_node = _DRIVE_LINK_SOURCE_NODE[node_name]
        assert f"$('{source_node}').item.json.id" in drive_link_expression, (
            f"{node_name}: 'Drive Link' ({drive_link_expression!r}) doesn't reference "
            f"$('{source_node}').item.json.id"
        )
        assert "https://drive.google.com/file/d/" in drive_link_expression, (
            f"{node_name}: 'Drive Link' ({drive_link_expression!r}) doesn't build a "
            "drive.google.com/file/d/... URL"
        )


def test_receivables_schedule_trigger_is_disabled_by_default():
    path = WORKFLOWS_DIR / "receivables.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    assert workflow.get("active") is False

    schedule_nodes = [n for n in _iter_nodes(workflow) if n.get("type") == "n8n-nodes-base.scheduleTrigger"]
    assert schedule_nodes, "Expected a Schedule Trigger node in receivables.json"
    for node in schedule_nodes:
        assert node.get("disabled") is True, f"Schedule Trigger node {node.get('name')!r} must be disabled by default"
