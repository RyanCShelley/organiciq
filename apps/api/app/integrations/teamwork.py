"""Pushing a prescribed action into Teamwork as a task.

One direction only. Teamwork owns the task once it exists — its status, its
comments, its reassignment — and OrganicIQ keeps the id so the slot card can
link to it. Reading status back is a second job needing a webhook or a poll,
and pretending to do it with a one-shot create would put a stale status beside
a live one.

Configuration is per install, not per client, except the tasklist: one
Teamwork site, one API token, and a tasklist id mapped to each client. Until
`TEAMWORK_SITE` and `TEAMWORK_API_TOKEN` are set, `configured()` is False and
the page offers Copy instead of Send.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

import httpx

#: Teamwork's own cap on a task name.
MAX_NAME = 255
TIMEOUT_SECONDS = 20.0


@dataclass(frozen=True)
class TeamworkConfig:
    site: str
    token: str

    @property
    def base_url(self) -> str:
        site = self.site.strip().rstrip("/")
        if site.startswith("http://") or site.startswith("https://"):
            return site
        if "." not in site:
            site = f"{site}.teamwork.com"
        return f"https://{site}"

    @property
    def auth_header(self) -> str:
        # Teamwork takes the API token as the basic-auth username with any
        # password; "x" is the documented placeholder.
        raw = f"{self.token}:x".encode()
        return "Basic " + base64.b64encode(raw).decode()


class TeamworkError(RuntimeError):
    """A push that did not land, with Teamwork's own words where it gave any."""


def load_config() -> TeamworkConfig | None:
    site = (os.getenv("TEAMWORK_SITE") or "").strip()
    token = (os.getenv("TEAMWORK_API_TOKEN") or "").strip()
    if not site or not token:
        return None
    return TeamworkConfig(site=site, token=token)


def configured() -> bool:
    return load_config() is not None


def task_body(
    *,
    title: str,
    why: str | None,
    done_when: str | None,
    target_url: str | None,
    metric: str | None,
    check_on: str | None,
    effort_min: int | None,
    record_url: str | None,
) -> tuple[str, str]:
    """The task's name and description.

    Everything the engine knows that the person doing the work needs, and
    nothing that only makes sense beside the other nine slots. A task read in
    Teamwork three weeks from now has no page around it.
    """
    name = title.strip()[:MAX_NAME]
    lines: list[str] = []
    if target_url:
        lines.append(f"Page: {target_url}")
    if why:
        lines.append("")
        lines.append("Why this page")
        lines.append(why)
    if done_when:
        lines.append("")
        lines.append("Done when")
        lines.append(done_when)
    if metric or check_on:
        lines.append("")
        measured = f"Measured on {metric}" if metric else "Measured"
        if check_on:
            measured += f", checked {check_on}"
        lines.append(measured)
    if effort_min:
        lines.append(f"Estimated {effort_min} minutes")
    if record_url:
        lines.append("")
        lines.append(f"From the OrganicIQ run: {record_url}")
    return name, "\n".join(lines)


def create_task(
    *,
    tasklist_id: str,
    name: str,
    description: str,
    due: str | None = None,
    assignee_teamwork_id: str | None = None,
    config: TeamworkConfig | None = None,
    client: httpx.Client | None = None,
) -> dict:
    """Create one task and return `{id, url}`.

    `due` is an ISO date, which is what v3's `dueAt` takes (`format: date` in
    its OpenAPI). v1 wanted `YYYYMMDD`; copying that into a v3 call is how the
    first real send would have been rejected.
    """
    config = config or load_config()
    if config is None:
        raise TeamworkError(
            "Teamwork is not configured. Set TEAMWORK_SITE and TEAMWORK_API_TOKEN."
        )
    if not tasklist_id:
        raise TeamworkError(
            "This client has no Teamwork tasklist yet, so there is nowhere to send it."
        )

    payload: dict = {"task": {"name": name, "description": description}}
    if due:
        payload["task"]["dueAt"] = due
    if assignee_teamwork_id:
        payload["task"]["assignees"] = {"userIds": [int(assignee_teamwork_id)]}

    url = f"{config.base_url}/projects/api/v3/tasklists/{tasklist_id}/tasks.json"
    headers = {
        "Authorization": config.auth_header,
        "Content-Type": "application/json",
    }

    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise TeamworkError(f"Teamwork did not answer: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    if response.status_code >= 400:
        detail = response.text[:300]
        raise TeamworkError(f"Teamwork refused the task ({response.status_code}): {detail}")

    try:
        body = response.json()
    except ValueError as exc:
        raise TeamworkError("Teamwork returned something that was not JSON.") from exc

    task = body.get("task") or {}
    task_id = task.get("id")
    if task_id is None:
        raise TeamworkError("Teamwork accepted the task but returned no id.")
    return {
        "id": str(task_id),
        "url": f"{config.base_url}/app/tasks/{task_id}",
    }


@dataclass(frozen=True)
class TaskList:
    """One tasklist, with the project it belongs to.

    The project is what makes the list choosable: "Content" means nothing on
    its own when nine clients each have one.
    """

    id: str
    name: str
    project_id: str | None = None
    project_name: str | None = None


#: Teamwork pages these, and an agency has more lists than one page holds.
TASKLIST_PAGE_SIZE = 250
MAX_TASKLIST_PAGES = 8


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_tasklists(body: dict) -> list[TaskList]:
    """Tasklists from a v3 response, with project names where they came.

    v3 returns related records in a sidecar `included` object keyed by id
    rather than nested in each row, so the project name has to be looked up
    rather than read off the tasklist.
    """
    projects = {}
    included = body.get("included")
    if isinstance(included, dict):
        for key, value in (included.get("projects") or {}).items():
            if isinstance(value, dict):
                projects[str(key)] = _as_text(value.get("name"))

    out: list[TaskList] = []
    for row in body.get("tasklists") or []:
        if not isinstance(row, dict):
            continue
        list_id = _as_text(row.get("id"))
        if not list_id:
            continue
        # The project arrives as an id, or as a small object, depending on
        # what was asked for.
        project = row.get("project")
        project_id = _as_text(row.get("projectId"))
        if isinstance(project, dict):
            project_id = _as_text(project.get("id")) or project_id
        elif project is not None and project_id is None:
            project_id = _as_text(project)
        out.append(
            TaskList(
                id=list_id,
                name=_as_text(row.get("name")) or f"Tasklist {list_id}",
                project_id=project_id,
                project_name=projects.get(project_id or ""),
            )
        )
    return out


def list_tasklists(
    *,
    config: TeamworkConfig | None = None,
    client: httpx.Client | None = None,
) -> list[TaskList]:
    """Every tasklist the token can see, newest project first."""
    config = config or load_config()
    if config is None:
        raise TeamworkError(
            "Teamwork is not configured. Set TEAMWORK_SITE and TEAMWORK_API_TOKEN."
        )

    owns_client = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    found: list[TaskList] = []
    try:
        for page in range(1, MAX_TASKLIST_PAGES + 1):
            try:
                response = client.get(
                    f"{config.base_url}/projects/api/v3/tasklists.json",
                    params={
                        "page": page,
                        "pageSize": TASKLIST_PAGE_SIZE,
                        "include": "projects",
                        "showCompleted": "false",
                    },
                    headers={"Authorization": config.auth_header},
                )
            except httpx.HTTPError as exc:
                raise TeamworkError(f"Teamwork did not answer: {exc}") from exc

            if response.status_code in (401, 403):
                raise TeamworkError(
                    "Teamwork rejected the credentials. The API token is in your "
                    "profile under API & Mobile, and is not the account password."
                )
            if response.status_code >= 400:
                raise TeamworkError(
                    f"Teamwork refused the request ({response.status_code}): "
                    f"{response.text[:200]}"
                )
            try:
                body = response.json()
            except ValueError as exc:
                raise TeamworkError("Teamwork returned something that was not JSON.") from exc

            batch = parse_tasklists(body)
            found.extend(batch)
            if len(batch) < TASKLIST_PAGE_SIZE:
                break
    finally:
        if owns_client:
            client.close()

    found.sort(key=lambda t: ((t.project_name or "~").lower(), t.name.lower()))
    return found
