"""Shared utilities for harness hooks.

All hooks should call `if disabled(): return 0` at the top of main().
"""
import os


def disabled() -> bool:
    """Check if hooks are globally disabled via env var.

    Set HARNESS_HOOKS_ENABLED=0 to disable all harness hooks.
    Any other value (or unset) means enabled.
    """
    return os.environ.get("HARNESS_HOOKS_ENABLED", "1").strip() == "0"
