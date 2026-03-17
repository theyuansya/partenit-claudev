"""
Dependency tracker for multi-stage pipeline.

Stage dependency graph (from config.STAGE_PREREQUISITES):
  sys-analysis  ─┐
                  ├─→ development ─→ testing
  architecture  ─┘

Responsibilities:
  - Extract pipeline stage from Jira labels
  - Check that all prerequisite stages are Done
  - Find and trigger next stages when prerequisites are met
  - Detect when all stages for a parent task are complete
"""
from __future__ import annotations

import logging

from config import (
    PIPELINE_LABEL_PREFIX,
    STAGE_PREREQUISITES,
    STATUS_DONE,
    STATUS_IN_PROGRESS,
    ALL_STAGES,
)

logger = logging.getLogger("pipeline.deps")


def get_stage(labels: list[str]) -> str | None:
    """Extract pipeline stage name from Jira labels list.

    Example: ["pipeline:development", "backend"] → "development"
    """
    for label in labels:
        if label.startswith(PIPELINE_LABEL_PREFIX):
            return label[len(PIPELINE_LABEL_PREFIX):]
    return None


def get_subtask_stage_status(subtask: dict) -> tuple[str | None, str]:
    """Return (stage, status_name) for a subtask dict from get_subtasks()."""
    labels = subtask.get("labels", [])
    status = subtask.get("status", "")
    return get_stage(labels), status


def check_prerequisites_done(
    parent_key: str,
    stage: str,
    jira,  # JiraClient — avoid circular import
) -> bool:
    """Return True if all prerequisite stages for `stage` are Done.

    If `stage` has no prerequisites, returns True immediately.
    """
    required = STAGE_PREREQUISITES.get(stage, [])
    if not required:
        return True

    subtasks = jira.get_subtasks(parent_key)
    # Build map: stage → status
    stage_status: dict[str, str] = {}
    for sub in subtasks:
        s, status = get_subtask_stage_status(sub)
        if s:
            stage_status[s] = status

    for req in required:
        if stage_status.get(req, "").lower() != STATUS_DONE.lower():
            logger.debug(
                "[%s] prerequisite %s is '%s', not Done",
                parent_key,
                req,
                stage_status.get(req, "missing"),
            )
            return False
    return True


def trigger_next_stages(
    parent_key: str,
    completed_stage: str,
    jira,  # JiraClient
) -> list[str]:
    """After `completed_stage` moves to Done, find stages whose prerequisites
    are now all satisfied and transition them to In Progress.

    Returns list of triggered stage keys.
    """
    subtasks = jira.get_subtasks(parent_key)

    # Build current map: stage → (key, status)
    stage_info: dict[str, dict] = {}
    for sub in subtasks:
        s, status = get_subtask_stage_status(sub)
        if s:
            stage_info[s] = {"key": sub["key"], "status": status}

    triggered = []
    for stage, prereqs in STAGE_PREREQUISITES.items():
        if completed_stage not in prereqs:
            continue  # completed_stage is not a dependency for this stage

        info = stage_info.get(stage)
        if not info:
            continue  # subtask for this stage doesn't exist

        # Only trigger if currently To Do (not already running/done)
        if info["status"].lower() in (STATUS_IN_PROGRESS.lower(), STATUS_DONE.lower()):
            continue

        # Check ALL prerequisites are done (not just completed_stage)
        all_done = all(
            stage_info.get(p, {}).get("status", "").lower() == STATUS_DONE.lower()
            for p in prereqs
        )
        if not all_done:
            logger.debug("[%s] stage %s still waiting for other prereqs", parent_key, stage)
            continue

        logger.info("[%s] triggering stage %s (prereqs met)", parent_key, stage)
        jira.transition(info["key"], STATUS_IN_PROGRESS)
        jira.add_comment(
            info["key"],
            f"🤖 Все предпосылки выполнены ({', '.join(prereqs)} → Done). "
            f"Этап {stage} запущен автоматически.",
        )
        triggered.append(stage)

    return triggered


def all_stages_done(parent_key: str, jira) -> bool:
    """Return True if all pipeline stages for this parent are Done."""
    subtasks = jira.get_subtasks(parent_key)
    stage_status: dict[str, str] = {}
    for sub in subtasks:
        s, status = get_subtask_stage_status(sub)
        if s:
            stage_status[s] = status

    for stage in ALL_STAGES:
        if stage not in stage_status:
            return False  # subtask missing → not done
        if stage_status[stage].lower() != STATUS_DONE.lower():
            return False
    return True


def collect_artifact_context(parent_key: str, jira) -> dict[str, str]:
    """Collect text artifacts from completed analysis/architecture stages.

    Returns dict: {"sys-analysis": "...", "architecture": "..."}
    Used to enrich development/testing prompts.
    """
    from config import ARTIFACT_STAGES

    subtasks = jira.get_subtasks(parent_key)
    context: dict[str, str] = {}

    for sub in subtasks:
        stage, status = get_subtask_stage_status(sub)
        if stage not in ARTIFACT_STAGES:
            continue
        # Read comments from the artifact subtask
        comments = jira.get_comments(sub["key"])
        # Find last bot comment with artifact content
        artifact_text = ""
        for comment in reversed(comments):
            if "## " in comment or "# " in comment or len(comment) > 200:
                artifact_text = comment
                break
        if artifact_text:
            context[stage] = artifact_text

    return context
