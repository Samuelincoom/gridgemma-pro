"""Download a local Gemma 4 compatible GGUF model for GridGemma Pro setup."""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_REPO_ID = "ggml-org/gemma-4-E2B-it-GGUF"
MODELS_DIR = Path(__file__).resolve().parent / "models"
PREFERENCE_TERMS = ("q4", "gemma-4", "e2b", "e4b", "it")
LICENSE_MESSAGE = "Please accept the model license on Hugging Face, then rerun this script."


def main() -> int:
    try:
        from huggingface_hub import HfApi, hf_hub_download
        from huggingface_hub.errors import GatedRepoError, HfHubHTTPError, RepositoryNotFoundError
    except Exception as exc:
        print(f"huggingface_hub is not installed or could not be imported: {exc}")
        print("Run: python -m pip install huggingface_hub")
        return 1

    repo_id = os.environ.get("GRIDGEMMA_MODEL_REPO", DEFAULT_REPO_ID)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Checking Hugging Face repo: {repo_id}")
        files = HfApi().list_repo_files(repo_id=repo_id)
        gguf_files = [name for name in files if name.lower().endswith(".gguf")]
        if not gguf_files:
            print("No .gguf files were found in the selected repository.")
            return 1

        selected = choose_model_file(gguf_files)
        print(f"Downloading: {selected}")
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=selected,
            local_dir=str(MODELS_DIR),
        )
        print(f"Downloaded model to: {local_path}")
        print("Normal GridGemma Pro synthesis can now run offline.")
        return 0
    except (GatedRepoError, RepositoryNotFoundError, HfHubHTTPError) as exc:
        print(f"Could not download the model: {exc}")
        print(LICENSE_MESSAGE)
        return 1
    except Exception as exc:
        print(f"Model download failed: {exc}")
        print(LICENSE_MESSAGE)
        return 1


def choose_model_file(files: list[str]) -> str:
    def score(name: str) -> tuple[int, int, str]:
        lower = Path(name).name.lower()
        preference_score = sum(1 for term in PREFERENCE_TERMS if term in lower)
        q4_bonus = 4 if "q4" in lower else 0
        return preference_score + q4_bonus, -len(lower), lower

    return max(files, key=score)


if __name__ == "__main__":
    sys.exit(main())
