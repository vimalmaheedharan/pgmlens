"""PGM Lens connectors: Jira, GitLab, GitHub and a registry for third-party sources."""

from .base import (
    Connector,
    ConnectorError,
    HttpSession,
    available_connectors,
    create_connector,
    merge_datasets,
)
from .github import GitHubConfig, GitHubConnector
from .gitlab import GitLabConfig, GitLabConnector
from .jira import JiraConfig, JiraConnector

__all__ = [
    "Connector",
    "ConnectorError",
    "GitHubConfig",
    "GitHubConnector",
    "GitLabConfig",
    "GitLabConnector",
    "HttpSession",
    "JiraConfig",
    "JiraConnector",
    "available_connectors",
    "create_connector",
    "merge_datasets",
]
