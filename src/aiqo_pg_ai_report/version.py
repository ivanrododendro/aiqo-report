from __future__ import annotations

import logging
import sys
from functools import lru_cache
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version as pkg_version
from pathlib import Path

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_EMBEDDED_VERSION_FILE = Path(__file__).with_name("_version_generated.txt")


def _read_embedded_version() -> str | None:
    try:
        if _EMBEDDED_VERSION_FILE.exists():
            text = _EMBEDDED_VERSION_FILE.read_text(encoding="utf-8").strip()
            return text or None
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Unable to read embedded version file: %s", exc)
    return None


@lru_cache(maxsize=1)
def get_package_version() -> str:
    """Return the package version resolved from metadata, embedded file, or git tags."""
    try:
        return pkg_version("aiqo-pg-ai-report")
    except PackageNotFoundError:
        logger.debug("Distribution metadata not found for aiqo-pg-ai-report.")
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Unable to read package metadata version: %s", exc)

    embedded_version = _read_embedded_version()
    if embedded_version:
        return embedded_version

    if getattr(sys, "frozen", False):
        logger.debug("Running in frozen mode; skipping setuptools_scm lookup.")
        return "0.0.0"

    try:
        scm = import_module("setuptools_scm")
        return scm.get_version(root=_PROJECT_ROOT, fallback_version="0.0.0")
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Falling back to default version because setuptools_scm failed: %s", exc)
        return "0.0.0"


@lru_cache(maxsize=1)
def get_litellm_version() -> str:
    """Return the installed litellm version if available."""
    try:
        return pkg_version("litellm")
    except PackageNotFoundError:
        logger.debug("litellm not installed in current environment.")
        return "not installed"
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Unable to read litellm version: %s", exc)
        return "unknown"
