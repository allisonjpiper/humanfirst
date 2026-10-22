"""
Upload Human First to a Hugging Face Space (Docker).

    .venv/bin/hf auth login                     # once; paste a WRITE token from huggingface.co/settings/tokens
    .venv/bin/python deploy/deploy_space.py <hf-username>/humanfirst

Only the files the app needs are uploaded (no .env, database, report, or tests).
Set the Space secrets PORTKEY_API_KEY and ADMIN_PASSWORD yourself in the Space's Settings.
"""

import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]


def main(repo_id: str) -> None:
    api = HfApi()
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(
        repo_id=repo_id, repo_type="space", folder_path=str(ROOT),
        allow_patterns=["Dockerfile", ".dockerignore", "requirements.txt", "backend/**", "extension/**"],
        ignore_patterns=["**/__pycache__/**", "**/*.pyc", "backend/static/_*"],
        delete_patterns=["backend/**", "extension/**"],  # remove files deleted locally
        commit_message="Deploy Human First",
    )
    api.upload_file(repo_id=repo_id, repo_type="space", path_or_fileobj=str(ROOT / "deploy" / "space_README.md"),
                    path_in_repo="README.md", commit_message="Space README")
    print(f"Uploaded. Build status: https://huggingface.co/spaces/{repo_id}")
    print(f"App (after the build finishes): https://{repo_id.replace('/', '-').replace('_', '-').lower()}.hf.space")


if __name__ == "__main__":
    if len(sys.argv) != 2 or "/" not in sys.argv[1]:
        sys.exit("usage: deploy_space.py <hf-username>/<space-name>")
    main(sys.argv[1])
