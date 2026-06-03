"""JiraAgent — orchestrates natural-language Jira workflows via Claude.

The agent exposes four tools to Claude:
    create_issue    – create a new Jira issue
    search_issues   – query issues with JQL
    get_issue       – retrieve a single issue
    link_issues     – link two issues together

Claude drives the tool loop until it decides the task is complete.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from .client import JiraClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schemas (passed to Claude)
# ---------------------------------------------------------------------------

TOOLS: list[dict[str, Any]] = [
    {
        "name": "create_issue",
        "description": (
            "Create a new Jira issue. "
            "Use this when the user wants to file a bug, task, story, or epic."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Jira project key, e.g. PROJ",
                },
                "summary": {
                    "type": "string",
                    "description": "One-line issue title",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed issue description (optional)",
                    "default": "",
                },
                "type": {
                    "type": "string",
                    "description": "Issue type: Bug, Task, Story, Epic (default: Task)",
                    "default": "Task",
                },
                "priority": {
                    "type": "string",
                    "description": "Priority: Highest, High, Medium, Low, Lowest (default: Medium)",
                    "default": "Medium",
                },
            },
            "required": ["project", "summary"],
        },
    },
    {
        "name": "search_issues",
        "description": (
            "Search Jira issues using JQL (Jira Query Language). "
            "Use this to find existing issues, triaging, or sprint queries. "
            "Example JQL: 'project = PROJ AND sprint = \"current sprint\" AND status != Done'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "jql": {
                    "type": "string",
                    "description": "A valid JQL query string",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 20)",
                    "default": 20,
                },
            },
            "required": ["jql"],
        },
    },
    {
        "name": "get_issue",
        "description": "Retrieve full details for a single Jira issue by its key (e.g. PROJ-123).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Jira issue key, e.g. PROJ-123",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "link_issues",
        "description": (
            "Link two Jira issues together. "
            "Common link types: Blocks, Clones, Duplicates, Relates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from_key": {
                    "type": "string",
                    "description": "The issue key that is the source of the link",
                },
                "to_key": {
                    "type": "string",
                    "description": "The issue key that is the target of the link",
                },
                "link_type": {
                    "type": "string",
                    "description": "Type of link (default: Relates)",
                    "default": "Relates",
                },
            },
            "required": ["from_key", "to_key"],
        },
    },
]

SYSTEM_PROMPT = """\
You are a Jira project management assistant.  Your job is to help users
create, search, retrieve, and link Jira issues based on plain-English
descriptions.

Guidelines:
- Always use the tools provided; never make up issue keys or data.
- When creating issues, infer sensible defaults from context (priority,
  issue type) unless the user specifies.
- When searching, construct precise JQL to minimise noise.
- After completing an action, summarise what you did in one or two sentences.
- If you need more information, ask a brief clarifying question.
- Prefer to complete the requested task in as few tool calls as necessary.
"""


class JiraAgent:
    """High-level agent that translates natural language into Jira operations.

    Usage::

        agent = JiraAgent(project="PROJ")
        result = agent.run("Fix the login timeout bug in the auth service")
        print(result)
    """

    def __init__(
        self,
        project: str | None = None,
        jira_client: JiraClient | None = None,
        anthropic_client: anthropic.Anthropic | None = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        max_iterations: int = 10,
    ) -> None:
        self.default_project = project
        self.jira = jira_client or JiraClient()
        self._client = anthropic_client or anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, task: str, extra_context: str = "") -> str:
        """Execute a natural-language Jira task and return a plain-text summary."""
        user_content = task
        if self.default_project:
            user_content = f"[Default project: {self.default_project}]\n\n{user_content}"
        if extra_context:
            user_content = f"{user_content}\n\nAdditional context: {extra_context}"

        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_content}
        ]

        for iteration in range(self._max_iterations):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,  # type: ignore[arg-type]
                messages=messages,
            )
            logger.debug(
                "Iteration %d — stop_reason=%s blocks=%d",
                iteration,
                response.stop_reason,
                len(response.content),
            )

            # Append the full assistant response to the conversation.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                # Done — extract the final text answer.
                return self._extract_text(response.content)

            if response.stop_reason != "tool_use":
                # Unexpected stop reason; surface whatever text we have.
                return self._extract_text(response.content)

            # Handle tool calls.
            tool_results = self._execute_tools(response.content)
            messages.append({"role": "user", "content": tool_results})

        return "Agent reached maximum iteration limit without completing the task."

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute_tools(
        self, content_blocks: list[Any]
    ) -> list[dict[str, Any]]:
        """Execute every tool_use block and return tool_result blocks."""
        results: list[dict[str, Any]] = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue
            try:
                output = self._dispatch(block.name, block.input)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Tool %s failed: %s", block.name, exc)
                output = {"error": str(exc)}

            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(output, default=str),
                }
            )
        return results

    def _dispatch(self, name: str, inputs: dict[str, Any]) -> Any:
        """Route a tool call to the appropriate JiraClient method."""
        if name == "create_issue":
            return self.jira.create_issue(
                project=inputs["project"],
                summary=inputs["summary"],
                description=inputs.get("description", ""),
                issue_type=inputs.get("type", "Task"),
                priority=inputs.get("priority", "Medium"),
            )
        if name == "search_issues":
            return self.jira.search_issues(
                jql=inputs["jql"],
                max_results=inputs.get("max_results", 20),
            )
        if name == "get_issue":
            return self.jira.get_issue(key=inputs["key"])
        if name == "link_issues":
            return self.jira.link_issues(
                from_key=inputs["from_key"],
                to_key=inputs["to_key"],
                link_type=inputs.get("link_type", "Relates"),
            )
        raise ValueError(f"Unknown tool: {name}")

    @staticmethod
    def _extract_text(content_blocks: list[Any]) -> str:
        """Pull the concatenated text from a list of content blocks."""
        parts = [
            block.text
            for block in content_blocks
            if hasattr(block, "type") and block.type == "text"
        ]
        return "\n".join(parts).strip() or "(no text response)"
