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
_EMBEDDED_BUILD_DATE_FILE = Path(__file__).with_name("_build_date_generated.txt")


def _read_embedded_text(path: Path, description: str) -> str | None:
    try:
        if path.exists():
            text = path.read_text(encoding="utf-8").strip()
            return text or None
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Unable to read embedded %s file: %s", description, exc)
    return None


@lru_cache(maxsize=1)
def get_package_version() -> str:
    """Return the package version resolved from embedded file, metadata, or git tags."""
    embedded_version = _read_embedded_text(_EMBEDDED_VERSION_FILE, "version")
    if embedded_version:
        return embedded_version

    is_frozen = getattr(sys, "frozen", False)

    if not is_frozen:
        try:
            return pkg_version("aiqo-pg-ai-report")
        except PackageNotFoundError:
            logger.debug("Distribution metadata not found for aiqo-pg-ai-report.")
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.debug("Unable to read package metadata version: %s", exc)

        try:
            scm = import_module("setuptools_scm")
            return scm.get_version(root=_PROJECT_ROOT, fallback_version="0.0.0")
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.debug("Falling back to default version because setuptools_scm failed: %s", exc)
            return "0.0.0"

    # Frozen binary without embedded version falls back to a safe default.
    logger.debug("Running in frozen mode with no embedded version; defaulting to unknown.")
    return "unknown"


@lru_cache(maxsize=1)
def get_build_date() -> str:
    """Return the embedded build date if available."""
    embedded_build_date = _read_embedded_text(_EMBEDDED_BUILD_DATE_FILE, "build date")
    if embedded_build_date:
        return embedded_build_date

    logger.debug("No embedded build date found; defaulting to unknown.")
    return "unknown"


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
