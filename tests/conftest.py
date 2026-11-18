"""Shared pytest configuration for the one-tone test suite."""

import os
from pathlib import Path


def pytest_sessionstart():
    """Keep repository-relative fixture paths stable from either project root."""
    os.chdir(Path(__file__).resolve().parents[1])
