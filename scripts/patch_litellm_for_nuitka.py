"""Apply the LiteLLM source compatibility patch required by Nuitka."""

from __future__ import annotations

from importlib.metadata import distribution
from pathlib import Path


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
    source_path = Path(distribution("litellm").locate_file(RELATIVE_SOURCE_PATH))
    if not source_path.is_file():
        raise RuntimeError(f"Unable to locate {source_path}.")
    source = source_path.read_text(encoding="utf-8")
    if REPLACEMENT in source:
        print("LiteLLM Nuitka compatibility patch is already applied.")
        return
    if ORIGINAL not in source:
        raise RuntimeError(f"Unsupported LiteLLM source in {source_path}; compatibility patch was not applied.")

    source_path.write_text(source.replace(ORIGINAL, REPLACEMENT), encoding="utf-8")
    print(f"Applied LiteLLM Nuitka compatibility patch to {source_path}.")


if __name__ == "__main__":
    main()
