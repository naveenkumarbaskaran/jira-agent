"""Jira Cloud REST API client using httpx."""

from __future__ import annotations

import os
from typing import Any

import httpx


class JiraClient:
    """Thin REST wrapper for Jira Cloud.  Auth is via API token (Basic auth).

    Environment variables (all required unless passed explicitly):
        JIRA_BASE_URL   e.g. https://your-org.atlassian.net
        JIRA_USER_EMAIL e.g. you@example.com
        JIRA_API_TOKEN  API token from https://id.atlassian.com/manage-profile/security/api-tokens
    """

    def __init__(
        self,
        base_url: str | None = None,
        user_email: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ["JIRA_BASE_URL"]).rstrip("/")
        user_email = user_email or os.environ["JIRA_USER_EMAIL"]
        api_token = api_token or os.environ["JIRA_API_TOKEN"]

        self._http = httpx.Client(
            base_url=f"{self.base_url}/rest/api/3",
            auth=(user_email, api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def create_issue(
        self,
        project: str,
        summary: str,
        description: str = "",
        issue_type: str = "Task",
        priority: str = "Medium",
    ) -> dict[str, Any]:
        """Create a Jira issue and return the created issue object."""
        payload: dict[str, Any] = {
            "fields": {
                "project": {"key": project},
                "summary": summary,
                "issuetype": {"name": issue_type},
                "priority": {"name": priority},
            }
        }
        if description:
            # Jira Cloud uses the Atlassian Document Format (ADF) for descriptions.
            payload["fields"]["description"] = {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": description}],
                    }
                ],
            }
        response = self._http.post("/issue", json=payload)
        response.raise_for_status()
        return response.json()

    def get_issue(self, key: str) -> dict[str, Any]:
        """Fetch a single issue by key (e.g. PROJ-123)."""
        response = self._http.get(f"/issue/{key}")
        response.raise_for_status()
        return response.json()

    def search_issues(self, jql: str, max_results: int = 20) -> dict[str, Any]:
        """Search issues using JQL.  Returns the raw search response."""
        response = self._http.get(
            "/search",
            params={"jql": jql, "maxResults": max_results},
        )
        response.raise_for_status()
        return response.json()

    def link_issues(
        self,
        from_key: str,
        to_key: str,
        link_type: str = "Relates",
    ) -> dict[str, Any]:
        """Create a link between two issues.

        Common link_type values:
            Blocks, is blocked by, Clones, is cloned by,
            Duplicates, is duplicated by, Relates
        """
        payload = {
            "type": {"name": link_type},
            "inwardIssue": {"key": from_key},
            "outwardIssue": {"key": to_key},
        }
        response = self._http.post("/issueLink", json=payload)
        response.raise_for_status()
        # 201 Created returns an empty body
        return {"status": "linked", "from": from_key, "to": to_key, "type": link_type}

    def get_current_sprint(self, project: str) -> dict[str, Any] | None:
        """Return the active sprint for a project (requires Jira Software)."""
        # First, find the board for the project.
        boards_response = self._http.get(
            f"{self.base_url}/rest/agile/1.0/board",
            params={"projectKeyOrId": project},
        )
        boards_response.raise_for_status()
        boards = boards_response.json().get("values", [])
        if not boards:
            return None
        board_id = boards[0]["id"]

        sprints_response = self._http.get(
            f"{self.base_url}/rest/agile/1.0/board/{board_id}/sprint",
            params={"state": "active"},
        )
        sprints_response.raise_for_status()
        sprints = sprints_response.json().get("values", [])
        return sprints[0] if sprints else None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "JiraClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
