# Inspector API-Key / RBAC Notes

The Go inspector supports bearer-token protection through `INSPECTOR_TOKEN`.

## Example

```bash
INSPECTOR_TOKEN=test-token go run .
curl -H "Authorization: Bearer test-token" http://localhost:8088/metrics
Suggested roles
viewer: read lease health
operator: read metrics and trace exports
admin: full operational inspection
Safe claim

Faultline includes demo API-key protection and RBAC policy artifacts. It does not claim enterprise identity integration.
