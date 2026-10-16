import os

os.environ.setdefault(
    "GHOST_TENANT_KEYS",
    '{"test-key-shophive-demo-0123456789abcdef": "shophive_demo"}',
)
os.environ.setdefault("GHOST_PROVIDER", "mock")
os.environ.setdefault("GHOST_STORE", "memory")
os.environ.setdefault(
    "GHOST_CURSOR_API_KEY",
    "test-key-shophive-demo-0123456789abcdef",
)
os.environ.setdefault("GHOST_RATE_LIMIT_PER_MIN", "100000")
