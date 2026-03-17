#!/bin/bash
set -e

# ── Claude Code authentication ────────────────────────────────────────────────
# Option A (Railway/cloud): set ANTHROPIC_API_KEY — Claude CLI picks it up automatically
# Option B (local Docker): mount ~/.claude:/root/.claude:ro in docker-compose.yml
# Option C (any server): set CLAUDE_AUTH_JSON=<base64 of ~/.claude dir tarball>
#   Generate with: tar -czf - ~/.claude | base64 -w0

if [ -n "$CLAUDE_AUTH_JSON" ]; then
    echo "[entrypoint] Restoring ~/.claude/.credentials.json..."
    mkdir -p /root/.claude
    echo "$CLAUDE_AUTH_JSON" | base64 -d > /root/.claude/.credentials.json
    chmod 600 /root/.claude/.credentials.json
    echo "[entrypoint] Done."
fi

# ── Start pipeline ────────────────────────────────────────────────────────────
exec python main.py
