"""Artifact saver - saves outputs and snapshots to the artifacts directory."""

import json
import logging
import os
from datetime import datetime

from orchestrator.config import ARTIFACTS_DIR

logger = logging.getLogger("onjaro.hooks.artifacts")


def save_artifact(run_id: str, name: str, content: str, extension: str = "txt") -> str:
    """Save an artifact file and return the path."""
    run_dir = os.path.join(ARTIFACTS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%H%M%S")
    filename = f"{timestamp}_{name}.{extension}"
    path = os.path.join(run_dir, filename)

    with open(path, "w") as f:
        f.write(content)

    logger.info("Saved artifact: %s", path)
    return path


def save_json_artifact(run_id: str, name: str, data: dict) -> str:
    """Save a JSON artifact."""
    content = json.dumps(data, indent=2, default=str, ensure_ascii=False)
    return save_artifact(run_id, name, content, "json")


def save_diff_artifact(run_id: str, diff: str) -> str:
    """Save a git diff snapshot."""
    return save_artifact(run_id, "diff_snapshot", diff, "diff")


def save_error_artifact(run_id: str, error: str, context: dict = None) -> str:
    """Save an error summary artifact."""
    content = f"Error: {error}\n\n"
    if context:
        content += f"Context:\n{json.dumps(context, indent=2, default=str, ensure_ascii=False)}"
    return save_artifact(run_id, "error_summary", content, "txt")
