"""Prepare a patched LiteLLM copy for Nuitka without mutating installed packages."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys
from importlib.metadata import distribution


RELATIVE_SOURCE_PATH = "litellm/litellm_core_utils/streaming_chunk_builder_utils.py"
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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {Path(sys.argv[0]).name} <output-directory>")

    source_path = Path(distribution("litellm").locate_file(RELATIVE_SOURCE_PATH))
    if not source_path.is_file():
        raise RuntimeError(f"Unable to locate {source_path}.")

    package_source = source_path.parents[1]
    output_directory = Path(sys.argv[1]).resolve()
    package_destination = output_directory / "litellm"
    shutil.rmtree(package_destination, ignore_errors=True)
    output_directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(package_source, package_destination)

    patched_source_path = package_destination / source_path.relative_to(package_source)
    source = patched_source_path.read_text(encoding="utf-8")
    if REPLACEMENT in source:
        print("LiteLLM Nuitka compatibility patch is already applied.")
        return
    if ORIGINAL not in source:
        raise RuntimeError(f"Unsupported LiteLLM source in {patched_source_path}; compatibility patch was not applied.")

    patched_source_path.write_text(source.replace(ORIGINAL, REPLACEMENT), encoding="utf-8")
    print(f"Prepared patched LiteLLM source at {patched_source_path}.")


if __name__ == "__main__":
    main()
