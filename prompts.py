"""
Stage-specific Claude Code prompt builders.

Each function receives the issue dict + enrichment context and returns
a ready-to-use prompt string for `claude -p <prompt>`.

Stages:
  sys-analysis  → produce SYSTEM_ANALYSIS.md artifact
  architecture  → produce ARCHITECTURE_DECISION.md artifact
  development   → write code, open PR to stage branch
  testing       → write tests, push to dev branch
"""
from __future__ import annotations


# ── Shared header ─────────────────────────────────────────────────────────────

def _base_header(issue: dict) -> str:
    parent_summary = issue.get('parent_summary', issue['summary'])
    epic_section = ""
    if issue.get('epic_context'):
        epic_section = (
            "## Контекст эпика\n"
            f"{issue['epic_context']}\n\n"
        )

    desc_text = issue.get('description_text', '')
    desc_section = ""
    if desc_text:
        desc_section = (
            "## Описание родительской задачи\n"
            f"{desc_text}\n\n"
        )
    elif not desc_text:
        desc_section = (
            "## Описание родительской задачи\n"
            f"(Описание не заполнено. Ориентируйся на название задачи "
            f"и контекст эпика выше.)\n\n"
        )

    return (
        f"## Задача: {issue['parent_key']} — {parent_summary}\n\n"
        f"Подзадача: {issue['key']} | "
        f"Тип этапа: **{issue['stage']}** | "
        f"Приоритет: {issue.get('priority', 'Medium')}\n"
        f"Компоненты: {', '.join(issue.get('components', []) or [])}\n\n"
        + epic_section
        + desc_section
    )


def _common_rules() -> str:
    return (
        "## Правила\n"
        "1. Прочитай CLAUDE.md и ARCHITECTURE.md для контекста.\n"
        "2. Минимальные изменения — только то, что нужно по задаче.\n"
        "3. Если меняешь сервис — обнови ARCHITECTURE.md.\n"
        "4. НЕ рефакторь «заодно». НЕ создавай git-коммиты.\n"
        "5. Непонятно → оставь TODO с объяснением.\n"
    )


# ── Stage: sys-analysis ────────────────────────────────────────────────────────

def build_sys_analysis_prompt(issue: dict) -> str:
    """Prompt for sys-analysis stage.

    Output: SYSTEM_ANALYSIS.md in repo root (Claude Code writes the file,
    pipeline reads it and posts to Jira as a comment).
    """
    jira_domain = issue.get("jira_domain", "")
    parent_url = f"https://{jira_domain}/browse/{issue['parent_key']}" if jira_domain else issue['parent_key']
    subtask_url = f"https://{jira_domain}/browse/{issue['key']}" if jira_domain else issue['key']

    file_header = (
        f"# Системный анализ: [{issue['parent_key']}]({parent_url}) — {issue['summary']}\n\n"
        f"> **Jira:** [{issue['parent_key']}]({parent_url}) · "
        f"Подзадача: [{issue['key']}]({subtask_url})  \n"
        f"> **Этап:** sys-analysis  \n"
        f"> Сгенерировано автоматически Trust Layer Pipeline\n\n"
        "---\n\n"
    )

    return (
        _base_header(issue)
        + "## Что нужно сделать: Системный анализ\n\n"
        "Проведи системный анализ задачи и создай файл `SYSTEM_ANALYSIS.md` в корне репозитория.\n\n"
        f"Файл ДОЛЖЕН начинаться ровно с этого заголовка (скопируй дословно):\n\n"
        f"```\n{file_header}```\n\n"
        "Затем добавь разделы:\n"
        "1. **Краткое описание проблемы** — что именно требуется изменить/добавить\n"
        "2. **Затронутые компоненты** — список сервисов/библиотек, которые нужно изменить\n"
        "3. **Зависимости** — что ещё может быть затронуто (upstream/downstream)\n"
        "4. **Риски** — потенциальные проблемы при реализации\n"
        "5. **Граничные случаи** — нестандартные ситуации, которые нужно обработать\n"
        "6. **Рекомендованный подход** — 2-3 предложения о том, как реализовать\n\n"
        "Формат: markdown заголовки, списки, примеры кода где нужно.\n"
        "Объём: 300-600 строк — подробно, но по делу.\n\n"
        + _common_rules()
    ).strip()


# ── Stage: architecture ────────────────────────────────────────────────────────

def build_architecture_prompt(issue: dict, sys_analysis: str = "") -> str:
    """Prompt for architecture stage.

    Output: ARCHITECTURE_DECISION.md in repo root.
    """
    jira_domain = issue.get("jira_domain", "")
    parent_url = f"https://{jira_domain}/browse/{issue['parent_key']}" if jira_domain else issue['parent_key']
    subtask_url = f"https://{jira_domain}/browse/{issue['key']}" if jira_domain else issue['key']

    file_header = (
        f"# Архитектурное решение: [{issue['parent_key']}]({parent_url}) — {issue['summary']}\n\n"
        f"> **Jira:** [{issue['parent_key']}]({parent_url}) · "
        f"Подзадача: [{issue['key']}]({subtask_url})  \n"
        f"> **Этап:** architecture  \n"
        f"> Сгенерировано автоматически Trust Layer Pipeline\n\n"
        "---\n\n"
    )

    context_section = ""
    if sys_analysis:
        context_section = (
            "## Результат системного анализа (предыдущий этап)\n\n"
            f"{sys_analysis[:3000]}\n\n"
        )

    return (
        _base_header(issue)
        + context_section
        + "## Что нужно сделать: Архитектурное решение\n\n"
        "Изучи системный анализ (если есть) и создай файл `ARCHITECTURE_DECISION.md` в корне репозитория.\n\n"
        f"Файл ДОЛЖЕН начинаться ровно с этого заголовка (скопируй дословно):\n\n"
        f"```\n{file_header}```\n\n"
        "Затем добавь разделы:\n"
        "Файл должен содержать:\n"
        "1. **Контекст** — кратко, почему мы делаем это изменение\n"
        "2. **Решение** — конкретное архитектурное решение с обоснованием\n"
        "3. **Альтернативы** — что рассматривалось и почему отклонено\n"
        "4. **API контракт** — новые/изменённые эндпоинты, форматы данных\n"
        "5. **Схема данных** — если меняются модели или хранилища\n"
        "6. **Последовательность** — порядок реализации (что делать в dev-этапе)\n"
        "7. **Метрики успеха** — как понять что задача выполнена\n\n"
        "Важно: учитывай принципы Trust Layer из CLAUDE.md:\n"
        "- L1/L2a должны остаться детерминированными и синхронными\n"
        "- Все решения должны fail-closed\n"
        "- Не смешивай слои L1, L2a, L2b, L3\n\n"
        + _common_rules()
    ).strip()


# ── Stage: development ─────────────────────────────────────────────────────────

def build_development_prompt(
    issue: dict,
    sys_analysis: str = "",
    architecture: str = "",
) -> str:
    """Prompt for development stage.

    Output: code changes + PR to stage branch.
    """
    context_parts = []
    if sys_analysis:
        context_parts.append(
            "## Системный анализ\n\n" + sys_analysis[:2000]
        )
    if architecture:
        context_parts.append(
            "## Архитектурное решение\n\n" + architecture[:2000]
        )
    context_section = ("\n\n".join(context_parts) + "\n\n") if context_parts else ""

    safety_warning = ""
    if issue.get("safety_relevant"):
        safety_warning = (
            "## ⚠️ SAFETY-RELEVANT\n"
            "Прочитай STEERING.md §4 перед работой. "
            "L1/L2a — без ML, без network I/O. Fail-closed. audit_ref обязателен.\n\n"
        )

    return (
        _base_header(issue)
        + safety_warning
        + context_section
        + "## Что нужно сделать: Реализация\n\n"
        "Реализуй задачу согласно архитектурному решению (если есть) или по описанию.\n\n"
        "Алгоритм работы:\n"
        f"1. Прочитай ARCHITECTURE_DECISION_{issue['parent_key']}.md и "
        f"SYSTEM_ANALYSIS_{issue['parent_key']}.md (если есть в репо).\n"
        "2. Найди файлы для изменения — не угадывай, читай код.\n"
        "3. Реализуй минимальными изменениями — только то, что нужно.\n"
        "4. Напиши тесты (pytest) для нового кода.\n"
        "5. Убедись что `pytest tests/` проходит.\n"
        "6. Обнови ARCHITECTURE.md если изменил/добавил сервис.\n\n"
        "НЕ создавай git-коммиты и PR — это сделает pipeline.\n\n"
        + _common_rules()
    ).strip()


# ── Stage: testing ─────────────────────────────────────────────────────────────

def build_testing_prompt(
    issue: dict,
    sys_analysis: str = "",
    architecture: str = "",
) -> str:
    """Prompt for testing stage.

    Output: new/updated test files, no PR needed (pipeline pushes to dev branch).
    """
    context_parts = []
    if sys_analysis:
        context_parts.append("## Системный анализ\n\n" + sys_analysis[:1500])
    if architecture:
        context_parts.append("## Архитектурное решение\n\n" + architecture[:1500])
    context_section = ("\n\n".join(context_parts) + "\n\n") if context_parts else ""

    return (
        _base_header(issue)
        + context_section
        + "## Что нужно сделать: Тестирование\n\n"
        "Напиши исчерпывающие тесты для реализованных изменений.\n\n"
        "Что должно быть покрыто:\n"
        "1. **Happy path** — стандартное использование\n"
        "2. **Edge cases** — граничные значения, пустые входы, максимальные значения\n"
        "3. **Error cases** — некорректные входные данные, недоступные зависимости\n"
        "4. **Safety invariants** — если задача safety-relevant: тесты на fail-closed поведение\n\n"
        "Правила для тестов:\n"
        "- Используй pytest\n"
        "- НЕ мокируй реальные зависимости без необходимости (см. CLAUDE.md)\n"
        "- Тесты должны быть детерминированными (нет time.sleep, нет random без seed)\n"
        "- Каждый тест проверяет одну вещь\n"
        "- Имена тестов: `test_<что>_<когда>_<ожидаемый результат>`\n\n"
        "Запусти `pytest tests/ -v` и убедись что всё зелёное.\n"
        "НЕ создавай git-коммиты — это сделает pipeline.\n\n"
        + _common_rules()
    ).strip()


# ── Router ─────────────────────────────────────────────────────────────────────

def build_stage_prompt(issue: dict, artifact_context: dict) -> str:
    """Route to the correct prompt builder based on issue['stage']."""
    stage = issue.get("stage", "")
    sys_analysis = artifact_context.get("sys-analysis", "")
    architecture = artifact_context.get("architecture", "")

    if stage == "sys-analysis":
        return build_sys_analysis_prompt(issue)
    elif stage == "architecture":
        return build_architecture_prompt(issue, sys_analysis=sys_analysis)
    elif stage == "development":
        return build_development_prompt(
            issue, sys_analysis=sys_analysis, architecture=architecture
        )
    elif stage == "testing":
        return build_testing_prompt(
            issue, sys_analysis=sys_analysis, architecture=architecture
        )
    else:
        # Fallback: generic prompt
        from orchestrator import build_claude_prompt
        return build_claude_prompt(issue, {"type": "feature", "complexity": "medium",
                                            "needs_tests": True, "safety_relevant": False,
                                            "main_files": []})
