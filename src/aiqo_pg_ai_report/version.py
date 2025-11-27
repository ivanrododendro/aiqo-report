from __future__ import annotations

import logging
from pathlib import Path
from functools import lru_cache

from importlib.metadata import PackageNotFoundError, version as pkg_version
from setuptools_scm import get_version

logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_package_version() -> str:
    """Return the package version resolved from git tags."""
    try:
        return get_version(root=_PROJECT_ROOT, fallback_version="0.0.0")
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
