from __future__ import annotations

import json
from pathlib import Path

from app.models.project import Project
from app.settings import PROJECT_EXTENSION


class ProjectError(Exception):
    """Raised when a project file cannot be loaded or saved."""


class ProjectManager:
    @staticmethod
    def save(project: Project, path: str | Path) -> Path:
        target = Path(path)
        if target.suffix.lower() != PROJECT_EXTENSION:
            target = target.with_suffix(PROJECT_EXTENSION)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                json.dumps(project.to_dict(), indent=4),
                encoding="utf-8",
            )
        except OSError as exc:
            raise ProjectError(f"Unable to save project: {exc}") from exc
        return target

    @staticmethod
    def load(path: str | Path) -> Project:
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ProjectError(f"Unable to open project: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ProjectError(f"Invalid project JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ProjectError("Project file must contain a JSON object.")
        try:
            return Project.from_dict(data)
        except (TypeError, ValueError) as exc:
            raise ProjectError(f"Invalid project data: {exc}") from exc
