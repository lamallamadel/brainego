# LoRA kill-switch and rollback procedure

This document defines how to quickly disable LoRA adapters and safely rollback to a known-good version (or base model) when regressions are detected.

## Runtime controls

The learning engine now exposes control endpoints:

- `GET /lora/status`: inspect LoRA state (`enabled`, `active_adapter_version`, rollback history).
- `POST /lora/disable`: kill-switch that disables LoRA usage and falls back to base model.
- `POST /lora/enable`: re-enable LoRA usage, optionally pinning `adapter_version`.
- `POST /lora/rollback`: rollback adapter state to a target version or base model fallback.

### Environment flags

- `LORA_ENABLED` (`true`/`false`): default boot-time LoRA state.
- `ACTIVE_LORA_ADAPTER` (optional): initial adapter version at startup.

## Rollback runbook

### Trigger conditions

Use rollback immediately when one of the following is observed after adapter deploy:

- sustained latency increase or error-rate increase,
- quality regression from human feedback,
- safety/policy regression linked to a specific adapter version.

### Fast rollback to base model (kill-switch)

1. Inspect current status:

```bash
curl -X GET http://localhost:8003/lora/status
```

2. Disable LoRA:

```bash
curl -X POST http://localhost:8003/lora/disable \
  -H 'Content-Type: application/json' \
  -d '{"reason":"regression_detected"}'
```

3. Confirm `enabled=false` and `active_adapter_version=null`.

### Rollback to previous adapter

If LoRA should remain enabled but current adapter is unhealthy:

```bash
curl -X POST http://localhost:8003/lora/rollback \
  -H 'Content-Type: application/json' \
  -d '{"reason":"rollback_to_previous"}'
```

To rollback to a specific version:

```bash
curl -X POST http://localhost:8003/lora/rollback \
  -H 'Content-Type: application/json' \
  -d '{"adapter_version":"v1.2","reason":"rollback_to_known_good"}'
```

### Re-enable after mitigation

```bash
curl -X POST http://localhost:8003/lora/enable \
  -H 'Content-Type: application/json' \
  -d '{"adapter_version":"v1.2","reason":"post_incident_reenable"}'
```

## Operational notes

- Adapter deployment is blocked while kill-switch is active (`409 Conflict`).
- Every rollback operation appends an entry to `rollback_history` for auditing.
- Keep canary and monitoring checks in place before re-enabling new adapters.
