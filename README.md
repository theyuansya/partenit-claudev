# Trust Layer Dev Pipeline (`_pipeline/`)

Сервис, который принимает вебхуки из Jira, через DeepSeek готовит промпт, запускает Claude Code (Max) на задачу, пушит ветку в GitHub и создаёт PR, а затем обновляет задачу в Jira.

Папка `_pipeline` отдельно от основного кода Trust Layer, чтобы ничего не мешалось.

---

## 1. Что он делает

Поток для одной Jira‑задачи:

1. Jira отправляет `POST /webhook/jira?secret=...` c JSON события.
2. `main.py` проверяет `WEBHOOK_SECRET`, статус задачи (`TRIGGER_STATUS`, по умолчанию `Ready for Dev`) и тип (Task/Bug/Story…).
3. Создаётся job в памяти (`queued`) и в фоне запускается `worker.run_job(job)`.
4. `worker.py`:
   - помечает задачу в Jira в `In Development` и пишет комментарий с `job_id`;
   - через DeepSeek (`orchestrator.py`) конвертирует описание тикета (ADF JSON) в markdown, классифицирует задачу, собирает промпт для Claude Code;
   - `git clone` репозитория Trust Layer, создаёт ветку `feature/<ISSUE_KEY>`;
   - запускает `claude` CLI с этим промптом (использует Max‑подписку и авторизацию из `~/.claude`);
   - смотрит изменённые/новые файлы, при их наличии вызывает DeepSeek для анализа результата;
   - делает `git commit` и `git push` ветки;
   - создаёт PR в GitHub в ветку `STAGE_BRANCH` (по умолчанию `stage`) и навешивает метки;
   - переводит Jira‑задачу в `In Review` и пишет комментарий с ссылкой на PR, числом файлов, статусом тестов и замечаниями.

Никаких ключей Anthropic через `.env` не используется — Claude Code берёт авторизацию из смонтированной папки `~/.claude`.

---

## 2. Подготовка (один раз)

### 2.1. Авторизация Claude Code на сервере

На своей машине, где уже работает Claude Code Max:

```bash
claude --version
claude -p "скажи ок" --output-format text
```

Если всё ок, скопируй папку авторизации на сервер:

```bash
scp -r ~/.claude user@SERVER_IP:~/
```

На сервере проверь:

```bash
ssh user@SERVER_IP
claude -p "скажи ок" --output-format text
```

Если не просит логин/код — Max‑подписка подтянулась корректно.

### 2.2. Настроить `.env`

На сервере:

```bash
cd ~/PycharmProjects/trust-layer/_pipeline
cp .env.example .env
```

Заполни в `.env`:

- `DEEPSEEK_API_KEY` — ключ DeepSeek.
- `JIRA_DOMAIN` / `JIRA_EMAIL` / `JIRA_API_TOKEN` / `JIRA_PROJECT_KEY`.
- `GITHUB_TOKEN` — токен с правами `repo` для trust-layer репозитория.
- `GITHUB_REPO` — `org/repo`, например `GradeBuilderSL/trust-layer`.
- `WEBHOOK_SECRET` — случайная строка, её же укажешь в настройках Jira webhook.
- Остальные значения можно оставить по умолчанию или поправить под себя.

### 2.3. HTTPS и nginx (если нужен внешний вебхук от Jira)

Это описано в `PROMPT_DEV_PIPELINE.md` (секция 1.2). Важно, чтобы Jira могла стучаться по `https://<твой-домен>/webhook/jira?secret=...` и nginx прокидывал запросы на `127.0.0.1:8090`.

---

## 3. Запуск сервиса

На сервере, в папке `_pipeline`:

```bash
cd ~/PycharmProjects/trust-layer/_pipeline
docker compose up --build -d
```

Проверка:

```bash
curl http://127.0.0.1:8090/health
# → {"status":"ok", ...}
```

---

## 4. Настройка Jira webhook

В Jira Cloud:

1. **Settings → System → Webhooks → Create webhook**.
2. URL:

   ```text
   https://YOUR_DOMAIN/webhook/jira?secret=WEBHOOK_SECRET_ИЗ_.env
   ```

3. Events:
   - Issue → updated / transitioned (или как минимум события изменения статуса).
4. В самом проекте убедись, что статус, с которого нужно запускать пайплайн, совпадает с `TRIGGER_STATUS` в `.env` (по умолчанию `Ready for Dev`).

Когда задача переходит в этот статус, Jira шлёт webhook, сервис создаёт job и начинает работу.

---

## 5. Подготовка Jira: workflow и права

Чтобы пайплайн мог автоматически переводить задачи и писать комментарии, в Jira должны быть:

### 5.1. Статусы и переходы

Минимально нужны три статуса (можно использовать стандартные Jira, как на скрине):

- `To Do` — бэклог, пайплайн его не трогает.
- `In Progress` — стартовый статус, из которого запускается пайплайн (`TRIGGER_STATUS`).
- `In Review` — статус после создания PR (`SUCCESS_STATUS`).

Проверь workflow проекта:

1. `Project settings → Workflows`.
2. Открой активный workflow.
3. Убедись, что эти статусы есть (по умолчанию в Simplified Workflow уже есть `To Do / In Progress / In Review / Done`).
4. Убедись, что есть переходы хотя бы:
   - из `To Do` → `In Progress`;
   - из `In Progress` → `In Review`.

Метод `JiraClient.transition()` ищет переход по **имени статуса**, поэтому важно, чтобы названия в Jira совпадали с `TRIGGER_STATUS` / `SUCCESS_STATUS` и целевыми статусами, которые мы передаём из `worker.py`.

### 5.2. Права пользователя

Пользователь, для которого ты создаёшь `JIRA_API_TOKEN`:

- должен иметь права в проекте:
  - **Browse / Edit / Transition Issues**;
  - **Add Comments**;
- `JIRA_EMAIL` в `.env` должен совпадать с email этого пользователя;
- `JIRA_PROJECT_KEY` — ключ проекта (например, `TRUST`).

Если этих прав нет, переходы и комментарии будут падать с 4xx‑ошибками, а пайплайн будет помечать job как `failed`.

---

## 6. Как смотреть статус задач

### 5.1. Через HTTP

- `GET /health` — общее состояние:

  ```bash
  curl http://127.0.0.1:8090/health
  ```

- `GET /jobs` — последние 20 job’ов:

  ```bash
  curl http://127.0.0.1:8090/jobs | jq
  ```

- `GET /jobs/{job_id}` — подробности по конкретному job’у.

### 5.2. Через Jira / GitHub

- В Jira в комментариях к задаче будут записи от пайплайна:
  - начало работы, ошибки, ссылка на PR и краткое резюме DeepSeek.
- В GitHub будет ветка `feature/<ISSUE_KEY>` и PR в ветку `STAGE_BRANCH`.

---

## 7. Остановка / обновление

Остановить:

```bash
cd ~/PycharmProjects/trust-layer/_pipeline
docker compose down
```

Перезапустить с обновлённым кодом:

```bash
git pull   # если ты обновила репозиторий
docker compose up --build -d
```

---

## 8. Что можно безопасно менять

- В `.env`:
  - статусы Jira (`TRIGGER_STATUS`, `SUCCESS_STATUS`),
  - ветку для PR (`STAGE_BRANCH`),
  - лимиты `MAX_CONCURRENT_JOBS`, `JOB_TIMEOUT_MINUTES`.
- В `worker.py` — политику именования веток, формат commit message/PR body.
- В `orchestrator.py` — промпты для DeepSeek и схему классификации.

Все сетевые ключи/секреты хранятся только в `.env` (не в коде). Anthropic API‑ключи не используются: Claude Code работает через уже смонтированную папку `~/.claude`.

