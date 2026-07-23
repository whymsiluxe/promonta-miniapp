## Summary

## Why

## Scope / affected modules

## User roles affected
- [ ] owner
- [ ] worker
- [ ] both

## UI screenshots (if applicable)

## API changes (if applicable)

## Database / data-store changes (if applicable)
Remember: no real migrations exist (flat JSON files) — describe how existing data is affected/migrated manually if the shape changes.

## Permission changes (if applicable)
Update `docs/ROLES_AND_PERMISSIONS.md` and `docs/SECURITY.md` if so.

## Security impact
Any new attack surface, data exposure, or permission relaxation? If yes, explain — don't just check the box.

## Manual test steps
No automated tests exist yet — describe exactly what you clicked through, per `docs/TESTING.md`.

## Documentation updated
- [ ] `docs/CHANGELOG.md`
- [ ] `docs/PROJECT_STATE.md`
- [ ] `docs/FEATURES.md` (if feature status changed)
- [ ] Other relevant docs (API/DATABASE/UI_UX/ROLES_AND_PERMISSIONS/SECURITY/DEPLOYMENT/ENVIRONMENT as applicable)

## Rollback plan
How to revert this on the VPS if it breaks something (see `docs/DEPLOYMENT.md#rollback`).

## Checklist
- [ ] No secrets committed (checked with a grep pass, not just visual scan)
- [ ] Manually verified per `docs/TESTING.md`
- [ ] Synced to VPS and restarted the relevant service, if this PR is being merged to deploy
