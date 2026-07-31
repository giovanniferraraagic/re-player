"""Helpers shared by the test modules.

Kept out of conftest.py because pytest does not expose conftest as an
importable module, and duplicating the skip condition in every file would let
the copies drift apart.
"""

from __future__ import annotations

import os

import pytest

TARGET_URL = "https://demo.playwright.dev/todomvc/"

requires_provider = pytest.mark.skipif(
    not os.environ.get("AZURE_OPENAI_API_KEY"),
    reason="no model provider configured",
)
