---
name: zeabur-deploy
description: Deploy this monorepo's services to Zeabur, fetch deployment logs, restart, or get status — wraps the official Zeabur CLI (npx zeabur@latest). Use when user wants to deploy to Zeabur, push a build, check production logs, or restart a service. Reads ZEABUR_TOKEN from environment (never logs it).
---

# Zeabur Deploy Skill

Wraps Zeabur's official CLI (`npx zeabur@latest`). Authentication via `ZEABUR_TOKEN`
env var (set from `.env`). Never echoes token to logs.

## When to use

- "Deploy the gateway to Zeabur"
- "Get the latest deployment status / runtime logs"
- "Restart the production service"
- "Set up a new project on Zeabur"

## Inputs

```json
{
  "action": "deploy" | "logs" | "status" | "restart" | "auth-check" | "list-projects" | "list-services",
  "service_name": "gateway",                     // required for logs/status/restart
  "project_name": "reliability-workbench",       // optional; uses ZEABUR_PROJECT env if absent
  "env_id": null,                                  // optional explicit environment id
  "log_type": "runtime" | "build",               // for action=logs only; default runtime
  "tail_lines": 200                                // for logs; default 200
}
```

## Outputs

```json
{
  "ok": true,
  "action": "deploy",
  "deployment_url": "https://reliability-workbench.zeabur.app",
  "service": "gateway",
  "project": "reliability-workbench",
  "stdout_tail": "...last 50 lines of output...",
  "elapsed_ms": 45000
}
```

## How it picks credentials

1. `ZEABUR_TOKEN` env var (preferred — set from `.env`)
2. If absent → exits with `auth_required` error suggesting `npx zeabur@latest auth login`

NEVER echoes token to stdout/stderr; only passes it as `--token` flag to the CLI.

## Action: deploy

```bash
cd <repo_root>
npx zeabur@latest deploy --token <token> -i=false
```

Returns the deployment URL after `--watch` waits for build to complete.

## Action: logs

```bash
npx zeabur@latest deployment log -t=<runtime|build> --token <token> \
    --service-name <service> --env-id <env-id>
```

## Action: restart

```bash
npx zeabur@latest service restart --token <token> \
    --service-name <service> --env-id <env-id>
```

## Failure modes

| Mode | Trigger | Handling |
|---|---|---|
| `auth_required` | no ZEABUR_TOKEN | exit 1 with hint |
| `npx_not_found` | Node/npm missing | exit 1 with install hint |
| `network_error` | Zeabur API unreachable | exit 1 |
| `service_not_found` | service_name not in project | exit 1 with `list-services` suggestion |
| `build_failed` | Zeabur build job failed | return tail of build log + non-ok |

## Cost & latency

- $0 (Zeabur CLI is free; service hosting is Zeabur's pricing)
- `deploy`: 30-180s (Docker build + Zeabur deployment pipeline)
- `logs`: 1-5s
- `restart`: 5-15s
- `status` / `auth-check`: < 5s

## Safety

- **Never logs token** — passes via `--token` flag, scrubbed from stdout
- **Read-only by default** for non-deploy actions (logs/status are safe)
- **`deploy` is idempotent in Zeabur's sense**: same code → same deployment ID

## How to invoke

```bash
echo '{"action":"auth-check"}' | python scripts/run.py
echo '{"action":"deploy","service_name":"gateway"}' | python scripts/run.py
echo '{"action":"logs","service_name":"gateway","log_type":"runtime"}' | python scripts/run.py
```
