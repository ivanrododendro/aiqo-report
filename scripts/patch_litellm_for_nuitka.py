"""Patch the installed LiteLLM source used by Nuitka in the build environment."""

from __future__ import annotations

import sys
from importlib import util
from importlib.metadata import distribution
from pathlib import Path


RELATIVE_SOURCE_PATH = "litellm/litellm_core_utils/streaming_chunk_builder_utils.py"
SUPPORTED_VERSION = "1.104.0"
ORIGINAL = '''    @staticmethod
    def _role_of_choice(choice: object) -> str:
        match choice:
            case StreamingChoices(delta=Delta(role=str() as role)) | {"delta": {"role": str() as role}} if role:
                return role
            case _:
                return "assistant"
'''
REPLACEMENT = '''    @staticmethod
    def _role_of_choice(choice: object) -> str:
        if isinstance(choice, dict):
            delta = choice.get("delta")
            role = delta.get("role") if isinstance(delta, dict) else None
        else:
            delta = getattr(choice, "delta", None)
            role = getattr(delta, "role", None)

        return role if isinstance(role, str) and role else "assistant"
'''


def installed_source() -> Path:
    package = distribution("litellm")
    if package.version != SUPPORTED_VERSION:
        raise RuntimeError(f"Unsupported LiteLLM {package.version}; expected {SUPPORTED_VERSION}.")

    source_path = Path(package.locate_file(RELATIVE_SOURCE_PATH)).resolve()
    if not source_path.is_file():
        raise RuntimeError(f"Unable to locate {source_path}.")

    spec = util.find_spec("litellm")
    if spec is None or spec.submodule_search_locations is None:
        raise RuntimeError("Cannot resolve the LiteLLM package used by Python.")
    resolved_package = Path(next(iter(spec.submodule_search_locations))).resolve()
    if resolved_package != source_path.parents[1]:
        raise RuntimeError(
            f"Python resolves LiteLLM at {resolved_package}, but the installed source is {source_path.parents[1]}."
        )
    return source_path


def main() -> None:
    if sys.argv[1:] not in ([], ["--check"]):
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} [--check]")

    source_path = installed_source()
    source = source_path.read_text(encoding="utf-8")

    if sys.argv[1:] == ["--check"]:
        if source.count(REPLACEMENT) != 1 or ORIGINAL in source:
            raise RuntimeError(f"LiteLLM source used by Nuitka is not patched: {source_path}")
        print(f"Verified LiteLLM {SUPPORTED_VERSION} Nuitka source: {source_path}")
        return

    if source.count(REPLACEMENT) == 1 and ORIGINAL not in source:
        print(f"LiteLLM Nuitka patch already applied: {source_path}")
        return
    if source.count(ORIGINAL) != 1:
        raise RuntimeError(f"Unsupported LiteLLM source in {source_path}; compatibility patch was not applied.")

    source_path.write_text(source.replace(ORIGINAL, REPLACEMENT), encoding="utf-8")
    print(f"Patched installed LiteLLM source: {source_path}")


if __name__ == "__main__":
    main()
