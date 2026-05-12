"""Environment-driven configuration.

All config comes from environment variables (.env file in dev). No config file
parsing here on purpose — keep configuration discoverable in one place.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Jira
    jira_base_url: str
    jira_email: str
    jira_api_token: str
    # True: Atlassian Cloud (email + API token). False: Server/DC (PAT only).
    jira_cloud: bool

    # GitHub
    github_token: str
    github_default_owner: str | None
    github_default_repo: str | None
    # None: public github.com. Set for GitHub Enterprise Server (GHES),
    # e.g. "https://alm-github.system.region.mycompany/api/v3"
    github_base_url: str | None

    # Workspace
    workspace_path: Path
    operation_log_dir: str
    design_doc_dir: str

    # Pipeline
    max_retries_per_stage: int

    # Skill mapping override (optional path to a forked skill_mapping.yaml)
    skill_mapping_path: Path | None

    # Project mapping (optional; enables multi-project routing if present)
    project_mapping_path: Path | None

    # Logging
    log_level: str

    @property
    def operation_log_root(self) -> Path:
        return self.workspace_path / self.operation_log_dir

    @property
    def design_doc_root(self) -> Path:
        return self.workspace_path / self.design_doc_dir

    @property
    def default_skill_mapping_path(self) -> Path:
        # Bundled with the package
        return Path(__file__).parent / "resources" / "skill_mapping.yaml"

    @property
    def effective_skill_mapping_path(self) -> Path:
        return self.skill_mapping_path or self.default_skill_mapping_path

    @property
    def has_project_mapping(self) -> bool:
        """Whether multi-project routing is configured."""
        return self.project_mapping_path is not None and self.project_mapping_path.exists()


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable {name} is not set. "
            f"See .env.example for the full list."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_config() -> Config:
    workspace = Path(_required("WORKSPACE_PATH")).expanduser().resolve()
    if not workspace.exists():
        raise RuntimeError(f"WORKSPACE_PATH does not exist: {workspace}")
    if not workspace.is_dir():
        raise RuntimeError(f"WORKSPACE_PATH is not a directory: {workspace}")

    skill_mapping = _optional("SKILL_MAPPING_PATH")
    project_mapping = _optional("PROJECT_MAPPING_PATH")
    jira_cloud_raw = _optional("JIRA_CLOUD", "true").lower()
    jira_cloud = jira_cloud_raw not in {"false", "0", "no", "off"}
    github_base_url = _optional("GITHUB_BASE_URL") or None

    return Config(
        jira_base_url=_required("JIRA_BASE_URL").rstrip("/"),
        jira_email=_required("JIRA_EMAIL"),
        jira_api_token=_required("JIRA_API_TOKEN"),
        jira_cloud=jira_cloud,
        github_token=_required("GITHUB_TOKEN"),
        github_default_owner=_optional("GITHUB_DEFAULT_OWNER") or None,
        github_default_repo=_optional("GITHUB_DEFAULT_REPO") or None,
        github_base_url=github_base_url,
        workspace_path=workspace,
        operation_log_dir=_optional("OPERATION_LOG_DIR", "docs/operations"),
        design_doc_dir=_optional("DESIGN_DOC_DIR", "docs/designs"),
        max_retries_per_stage=int(_optional("MAX_RETRIES_PER_STAGE", "3")),
        skill_mapping_path=Path(skill_mapping).expanduser().resolve() if skill_mapping else None,
        project_mapping_path=Path(project_mapping).expanduser().resolve() if project_mapping else None,
        log_level=_optional("LOG_LEVEL", "INFO"),
    )
