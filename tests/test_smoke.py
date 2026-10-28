"""Smoke test: confirms the src packages are importable so CI has something to run."""

import importlib


def test_src_packages_import():
    for package in [
        "src",
        "src.extract",
        "src.validate",
        "src.suppliers",
        "src.receivables",
        "src.reconcile",
        "src.pack",
    ]:
        importlib.import_module(package)
