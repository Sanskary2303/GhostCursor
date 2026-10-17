-- packages/sdk-server-python/ghost_cursor/sql/001_ghost_chat_schema.postgres.sql

-- 1. Conversational Sessions Table
CREATE TABLE ghost_chat_sessions (
    session_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(128) NOT NULL,
    title VARCHAR(255) DEFAULT 'New Conversation',
    summary TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ghost_sessions_user ON ghost_chat_sessions(tenant_id, user_id, updated_at DESC);

-- 2. Message History & Execution Audit Log Table
CREATE TABLE ghost_chat_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    session_id VARCHAR(64) NOT NULL REFERENCES ghost_chat_sessions(session_id) ON DELETE CASCADE,
    run_id VARCHAR(64),
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    tool_calls JSONB DEFAULT '[]'::jsonb,         -- Backend tools invoked (e.g. lookup_order)
    client_actions JSONB DEFAULT '[]'::jsonb,     -- Frontend actions dispatched (e.g. click, navigate)
    token_count INT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ghost_messages_session ON ghost_chat_messages(session_id, created_at ASC);
CREATE INDEX idx_ghost_messages_run ON ghost_chat_messages(run_id);

