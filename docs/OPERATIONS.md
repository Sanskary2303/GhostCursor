# Ghost Cursor Operations Guide

This guide covers production operations for Ghost Cursor.

---

## Table of Contents

- [Threat Model](#threat-model)
- [Production Checklist](#production-checklist)
- [HMAC-Signed Tool Loopback Protocol](#hmac-signed-tool-loopback-protocol)
- [Dependency Management](#dependency-management)
- [Troubleshooting](#troubleshooting)
- [Retention and Deletion](#retention-and-deletion)
- [Incident Response](#incident-response)

---

## Threat Model

### Attack Vectors

| Vector | Mitigation |
|--------|-----------|
| **Browser-to-Ghost direct** | Gateway proxy only - browser can only reach customer backend |
| **API key exposure** | Server-to-server only; never in browser bundles |
| **Brain exfiltration** | Canary markers + server-side validation |
| **SQL injection** | Parameterized queries via SQLAlchemy |
| **Prompt injection** | Limited context window; no untrusted user input in system prompt |
| **DDoS** | Rate limiting (60 req/min); request size limits (64 KiB) |
| **XSS via model** | Output sanitized; no raw HTML rendering |
| **CSRF** | Token-based; backend handles validation |

### Trusted Components

| Component | Trust Level |
|-----------|-------------|
| Ghost Cursor Orchestrator | High (GCP-managed) |
| Vertex AI | High (Google-managed) |
| Customer Backend SDK | Medium (customer code) |
| Frontend SDK | Medium (signed bundles) |

### Untrusted Components

| Component | Handling |
|-----------|----------|
| User input | Sanitized, bounded, never injected into system prompt |
| Brain files | Path traversal protection, forbidden pattern validation |
| Customer backend tools | Read-only enforced, output bounded |

---

## Production Checklist

### Pre-Deployment

- [ ] GCP project created with billing enabled
- [ ] Cloud SQL instance provisioned with regional HA
- [ ] Secret Manager populated with all keys
- [ ] Service account with minimal IAM created
- [ ] Docker images built and pushed to Artifact Registry
- [ ] Cloud Run service configured with min=1, max instances
- [ ] HTTPS load balancer configured
- [ ] Cloud Armor security policy enabled
- [ ] Monitoring dashboard created
- [ ] Log exports configured to BigQuery

### Environment Variables

```bash
# Ghost Cursor Orchestrator
GCP_PROJECT_ID=your-project
GCP_LOCATION=us-central1
DATABASE_URL=postgresql://...
GHOST_CURSOR_API_KEY=...
TENANT_API_KEY_1=...
USE_MOCK_LLM=false

# Customer Backend
GHOST_CURSOR_API_KEY=...
GHOST_CURSOR_TENANT_ID=shophive_demo
GHOST_CURSOR_BRAIN_DIR=./brain
```

### Security Hardening

1. **IAM最小权限**
   - `roles/run.invoker` for API invocation
   - `roles/secretmanager.secretAccessor` for secrets
   - `roles/aiplatform.user` for Vertex AI

2. **Network Security**
   - Private service connection to Cloud SQL
   - VPC Service Controls applied
   - No public IP on database

3. **Application Security**
   - Request size limits (64 KiB)
   - Rate limiting (60 req/min)
   - Origin header rejection
   - CSP headers

---

## HMAC-Signed Tool Loopback Protocol

To securely execute customer backend tools locally on customer infrastructure without exposing write keys or accepting forged tool calls, the orchestrator and gateways enforce an HMAC-SHA256 signature protocol on all `awaiting_tools` dispatches:

### Key Derivation
The loopback key is derived separately from the customer API key using HKDF-SHA256 (RFC 5869):
```
loopback_key = HKDF-SHA256(ikm=api_key, salt="", info="ghost-loopback-v1", length=32)
```
This isolates the bearer API key (used for server-to-server auth) from tool call authentication.

### Message & Signature Format
Before sending tool calls to the customer gateway, the orchestrator constructs a canonical message:
```
message = "{tenant}.{timestamp}.{runId}.{revision}.{canonical_json(toolCalls)}"
signature = HMAC-SHA256(loopback_key, message).hexdigest()
```
where `canonical_json` recursively sorts object keys with separators `(",", ":")` and UTF-8 encoding.
The signature is attached to the internal response:
```json
"loopbackSignature": {
  "v": 1,
  "ts": 1700000000,
  "sig": "<hex_signature>"
}
```

### Gateway Verification & Replay Protection
Customer gateways (Python and Node.js SDKs) verify the signature prior to dispatching any tool execution:
1. `loopbackSignature` must be present and contain `v == 1`.
2. `ts` must fall within $\pm 300$ seconds of the gateway's current clock.
3. Message HMAC matches in constant time (`hmac.compare_digest` / `crypto.timingSafeEqual`).
4. Any mismatch (expired timestamp, tampered parameters, mismatched tenant, wrong revision, or missing signature) fails closed immediately with `502 bad_tool_signature`. Tools are never executed on invalid signatures.
5. The signature is internal to the backend proxy: the browser-facing public projection automatically drops `loopbackSignature`.

---

## Dependency Management

### Python Dependencies

```bash
# Update dependencies
pip install --upgrade -r requirements.txt

# Freeze versions
pip freeze > requirements.lock.txt

# Check for vulnerabilities
pip-audit -r requirements.txt
```

### Frontend Dependencies

```bash
# Update packages
npm update

# Audit for vulnerabilities
npm audit

# Pin versions
npm install --package-lock-only
```

### Security Updates

| Dependency | Update Frequency | Alert Channel |
|-----------|-----------------|---------------|
| Python packages | Weekly | Snyk/Dependabot |
| Node packages | Weekly | Snyk/Dependabot |
| Base images | Monthly | Container analysis |

---

## Troubleshooting

### Common Errors

#### "Database connection failed"

```python
# Verify connection string
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Test connection
psql $DATABASE_URL -c "SELECT 1"
```

#### "Model not found"

```bash
# Enable Vertex AI
gcloud services enable aiplatform.googleapis.com

# Check model availability
gcloud ai models list --region=us-central1
```

#### "Tenant not found"

```python
# Verify API key mapping in orchestrator
valid_keys = {
    "tenant-1-secret-key": "tenant_1",
    "tenant-2-secret-key": "tenant_2",
}
```

#### "Brain file not found"

```bash
# Check file structure
ls -la brain/
ls -la brain/pages/

# Verify path in config
GHOST_CURSOR_BRAIN_DIR=./brain
```

### Log Locations

| Service | Log Query |
|---------|-----------|
| Cloud Run | `resource.type="cloud_run_revision"` |
| Cloud SQL | `resource.type="cloud_sql_database"` |
| Vertex AI | `protoPayload.methodName="google.cloud.aiplatform.v1.PredictionService.GenerateContent"` |

### Debug Mode

```bash
# Set logging level
export LOG_LEVEL=DEBUG

# Enable stack traces
export DEBUG=true
```

---

## Retention and Deletion

### Run State Retention

- **Ephemeral runs**: 30 minutes (auto-expired)
- **Active sessions**: Until completion or cancellation
- **Expired runs**: Deleted after 30 minutes + grace period

### Chat History Retention

- **Customer-owned**: Customer sets retention policy
- **Recommended**: 7 years (tax compliance)

### Data Deletion Process

```python
# Ghost Cursor: Delete expired runs
DELETE FROM ghost_runs WHERE expires_at < NOW() - INTERVAL '1 day';

# Customer DB: Delete old sessions (per customer policy)
DELETE FROM ghost_chat_sessions WHERE updated_at < NOW() - INTERVAL '7 years';
```

### GDPR Compliance

```bash
# Customer can request data export
SELECT * FROM ghost_chat_sessions WHERE user_id = ?;
SELECT * FROM ghost_chat_messages WHERE session_id IN (...);

# Customer can request deletion
DELETE FROM ghost_chat_sessions WHERE user_id = ?;
DELETE FROM ghost_chat_messages WHERE user_id = ?;
```

---

## Incident Response

### Security Incident

1. **Contain**: Disable affected tenant API keys
2. **Investigate**: Review Cloud Logging for suspicious activity
3. **Eradicate**: Patch vulnerability, rotate credentials
4. **Recover**: Restore from clean backup if needed
5. **Lessons**: Update documentation, add monitoring

### Service Outage

| Impact | Response |
|--------|----------|
| **Partial (1/5 instances)** | Wait for auto-recovery |
| **Full (all instances)** | Scale to max instances, check Cloud SQL |
| **Cloud SQL down** | Failover to replica, if available |

### Monitoring Alerts

| Alert | Threshold | Response |
|-------|-----------|----------|
| Error rate > 5% | 5 minutes | Check logs, rollback if needed |
| Latency > 5s | P95, 10 minutes | Scale instances, check DB |
| Memory > 90% | 5 minutes | Scale memory, investigate leak |
| Run count spike | > 2x normal | Investigate for DDoS |

### Runbook: Rollback

```bash
# Rollback Cloud Run service
gcloud run services update-traffic ghost-cursor-api \
  --to-revisions=ghost-cursor-api-00001=100

# Revert code changes
git revert HEAD~1
```

---

## Scaling

### Horizontal Scaling

| Setting | Current | Max |
|---------|---------|-----|
| Cloud Run instances | 1 | 5 |
| DB connections | 5 per instance | 100 |
| Concurrent connections | 5 per instance | 1000 |

### Vertical Scaling

| Resource | Current | Max |
|----------|---------|-----|
| Memory | 512 Mi | 32 Gi |
| CPU | 1 vCPU | 8 vCPU |
| DB tier | db-g1-small | db-n1-standard-8 |

### Auto-Scaling Configuration

```yaml
# Cloud Run
min_instances: 1  # Cold starts avoided
max_instances: 5  # Budget cap
concurrency: 5    # Requests per instance
```

---

## Cost Management

### Budget Alerts

```bash
gcloud billing budgets create \
  --billing-account=XXX \
  --display-name="ghost-cursor-budget" \
  --budget-amount=100 \
  --currency-code=USD \
  --threshold-settings=50%,80%,100%
```

### Cost Optimization

| Area | Optimization |
|------|--------------|
| Cloud Run | Set max_instances, use min_instances=1 |
| Vertex AI | Use Flash model, not Pro |
| Cloud SQL | Use regional HA, not multi-region |
| Logging | Export to BigQuery, set retention |

### Cost Breakdown

| Service | Monthly Cost | Notes |
|---------|--------------|-------|
| Cloud Run | $20-40 | 1M requests/month |
| Vertex AI | $5-20 | 10K conversations |
| Cloud SQL | $20-30 | PostgreSQL 17 |
| Cloud Storage | $5 | SDK bundle |
| **Total** | **$50-95** | Light production load |

---

## Maintenance

### Weekly Tasks

- [ ] Review error logs
- [ ] Check Cloud Monitoring dashboard
- [ ] Verify backup success
- [ ] Audit API key usage

### Monthly Tasks

- [ ] Update dependencies
- [ ] Review IAM permissions
- [ ] Check certificate expiration
- [ ] Review and clean up old runs

### Quarterly Tasks

- [ ] Security audit
- [ ] Performance review
- [ ] Capacity planning
- [ ] Disaster recovery test

---

## Contact

- **Security Issues**: security@ghostcursor.ai
- **Incident Response**: inc @ghostcursor.ai
- **Support**: support@ghostcursor.ai