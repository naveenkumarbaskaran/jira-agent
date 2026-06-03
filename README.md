# jira-agent-ai

An AI-powered CLI and Python library that creates, triages, and links Jira issues from plain-English descriptions.  It uses **Claude** (via the [Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python)) as the reasoning engine and the Jira Cloud REST API for persistence.

## Features

- **create** — describe a bug or task in plain English; the agent picks the right issue type, priority, and summary
- **triage** — get an AI-written sprint health overview with prioritised action items
- **link** — connect related issues with one sentence
- **search** — run raw JQL queries with a pretty table output
- **run** — free-form tasks ("create three sub-tasks for PROJ-42")

## Installation

```bash
pip install jira-agent-ai
# or, from source:
git clone https://github.com/your-org/jira-agent-ai
cd jira-agent-ai
pip install -e .
```

## Configuration

Set the following environment variables before using the tool:

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `JIRA_BASE_URL` | Your Jira Cloud base URL, e.g. `https://your-org.atlassian.net` |
| `JIRA_USER_EMAIL` | The email address of the Jira account used for API calls |
| `JIRA_API_TOKEN` | A Jira API token (create one at https://id.atlassian.com/manage-profile/security/api-tokens) |
| `JIRA_DEFAULT_PROJECT` | *(optional)* Default project key so you can omit `--project` |

## CLI Usage

### Create an issue

```bash
jira-agent create "Fix login timeout bug in auth service" --project PROJ
jira-agent create "Add dark mode to the dashboard" --project PROJ --type Story --priority High
```

### Triage a sprint

```bash
jira-agent triage --project PROJ
jira-agent triage --project PROJ --sprint "Sprint 14" --status "To Do,In Progress,Blocked"
```

### Free-form tasks

```bash
jira-agent run "Create a blocker link between PROJ-10 and PROJ-20" --project PROJ
jira-agent run "Find all open bugs assigned to alice@example.com in PROJ" --project PROJ
```

### Direct JQL search

```bash
jira-agent search "project = PROJ AND status = 'In Progress' ORDER BY updated DESC"
jira-agent search "assignee = currentUser() AND sprint in openSprints()" --max 50
```

## Python API

```python
from jira_agent import JiraAgent, JiraClient

# Auto-reads env vars
agent = JiraAgent(project="PROJ")

# Create an issue
result = agent.run("Fix the login timeout bug in the auth service")
print(result)

# Triage current sprint
result = agent.run("Triage all open issues in the current sprint")
print(result)

# Link issues
result = agent.run("Link PROJ-10 to PROJ-20 as Blocks")
print(result)

# Use the lower-level client directly
with JiraClient() as jira:
    issue = jira.create_issue(
        project="PROJ",
        summary="Add rate limiting to the API gateway",
        description="We need per-IP rate limiting to prevent abuse.",
        issue_type="Task",
        priority="High",
    )
    print(issue["key"])  # e.g. PROJ-123

    hits = jira.search_issues("project = PROJ AND status = Open ORDER BY created DESC")
    for iss in hits["issues"]:
        print(iss["key"], iss["fields"]["summary"])
```

## Architecture

```
jira_agent/
    __init__.py      re-exports JiraAgent and JiraClient
    agent.py         JiraAgent — Claude tool-use loop
    client.py        JiraClient — httpx-based Jira REST wrapper
    cli.py           Click CLI (create, triage, run, search)
```

### Tool-use loop

1. The user's plain-English task is sent to Claude with four tool definitions (`create_issue`, `search_issues`, `get_issue`, `link_issues`).
2. Claude calls whichever tools it needs, receiving JSON responses from the Jira REST API after each call.
3. The loop continues until Claude returns `stop_reason = "end_turn"` (or the iteration cap is hit).
4. The final text block from Claude's last response is returned to the caller.

## Development

```bash
pip install -e '.[dev]'
pytest
mypy jira_agent
ruff check jira_agent
```

## License

MIT
