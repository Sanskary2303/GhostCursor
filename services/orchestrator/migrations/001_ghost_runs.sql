CREATE TABLE IF NOT EXISTS ghost_runs (
    id UUID PRIMARY KEY,
    tenant VARCHAR(64) NOT NULL,
    subject VARCHAR(128) NOT NULL,
    request_id UUID NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    data JSONB NOT NULL,
    UNIQUE (tenant, subject, request_id)
);
CREATE INDEX IF NOT EXISTS idx_ghost_runs_expiry ON ghost_runs(expires_at);
CREATE INDEX IF NOT EXISTS idx_ghost_runs_tenant_subject ON ghost_runs(tenant, subject);

