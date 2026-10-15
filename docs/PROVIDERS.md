# LLM Provider Configuration

## Supported Providers

Ghost Cursor uses **Google Vertex AI with Gemini 2.0** as the default provider.

---

## Vertex AI (Recommended)

### Setup

1. Enable Vertex AI API in your GCP project:
```bash
gcloud services enable aiplatform.googleapis.com
```

2. Set up authentication:
```bash
gcloud auth application-default login
```

3. Configure environment variables:
```bash
export GCP_PROJECT_ID=your-gcp-project-id
export GCP_LOCATION=us-central1
export USE_MOCK_LLM=false
```

### Provider Configuration

| Setting | Environment Variable | Default |
|---------|---------------------|---------|
| Project ID | `GCP_PROJECT_ID` | Required |
| Location | `GCP_LOCATION` | `us-central1` |
| Model | - | `gemini-2.0-flash` |

### Available Models

| Model | Context Window | Use Case |
|-------|---------------|----------|
| `gemini-2.0-flash` | 1M tokens | Default, fast, cost-effective |
| `gemini-2.0-pro` | 1M tokens | Complex reasoning, multi-step tasks |

---

## Using a Different Provider

To use a different LLM provider, implement the `BaseVertexClient` interface:

```python
from ghost_cursor.llm.vertex import BaseVertexClient
from ghost_cursor.models.contracts import HostedRunResponse

class CustomProviderClient(BaseVertexClient):
    async def generate_content(
        self,
        agent,
        user_message: str,
        run_context: dict,
    ) -> HostedRunResponse:
        # Implement your provider's API call
        # Return HostedRunResponse object
        pass
```

Then inject your client into the orchestrator.

---

## Mock LLM for Development

For local development without GCP credentials:

```bash
export USE_MOCK_LLM=true
```

The mock provider returns deterministic responses based on message patterns:

| Message Pattern | Response |
|-----------------|----------|
| "dark mode" | Navigate to settings, toggle switch |
| "add to cart" | Navigate to product, click buttons |
| "checkout" | Ask for shipping address |
| "track" | Show guided tour |
| "order" | Call lookup_order tool |

---

## Provider Costs (Vertex AI)

### Gemini 2.0 Flash Pricing (approximate)

| Input Tokens | Output Tokens | Cost |
|--------------|---------------|------|
| 1M tokens | 1M tokens | ~$0.075 USD |

### Estimated Costs

| Usage | Input Tokens | Output Tokens | Monthly Cost |
|-------|-------------|---------------|--------------|
| Demo app (500 users/day) | 100K | 20K | ~$0.01 |
| Small app (5K users/day) | 1M | 200K | ~$0.10 |
| Medium app (50K users/day) | 10M | 2M | ~$1.00 |
| Large app (500K users/day) | 100M | 20M | ~$10.00 |

*Note: Costs vary by usage patterns and model selection.*

---

## Configuration Reference

### Orchestrator Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GCP_PROJECT_ID` | Yes (if not mock) | GCP project ID for Vertex AI |
| `GCP_LOCATION` | No | GCP region (default: us-central1) |
| `USE_MOCK_LLM` | No | Set to "true" for mock provider |
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `TENANT_API_KEY_1` | Yes | API key for tenant authentication |

### Backend SDK Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GHOST_CURSOR_API_KEY` | Yes | Server-to-server API key |
| `GHOST_CURSOR_TENANT_ID` | Yes | Tenant identifier |
| `GHOST_CURSOR_BRAIN_DIR` | No | Path to brain markdown files |
| `GHOST_CURSOR_SERVICE_URL` | No | Ghost Cloud URL (default: https://api.ghostcursor.ai) |

---

## Troubleshooting

### "Failed to initialize Vertex AI"

**Cause:** Missing GCP credentials or incorrect project ID.

**Solution:**
```bash
# Check credentials
gcloud auth application-default print-access-token

# Verify project
gcloud config get-value project
```

### "Model not found"

**Cause:** Invalid model name or region mismatch.

**Solution:** Ensure `GCP_LOCATION` matches where the model is available.

### Mock provider not responding

**Cause:** `USE_MOCK_LLM` not set correctly.

**Solution:**
```bash
export USE_MOCK_LLM=true  # Must be lowercase "true"
```

---

## Security Considerations

1. **Never commit API keys** - Use environment variables or Secret Manager
2. **Restrict IAM permissions** - Grant only required Vertex AI permissions
3. **Use service accounts** - Don't use user credentials in production
4. **Enable audit logging** - Track API usage for security review

### Minimal IAM Permissions

```json
{
  "roles/aiplatform.user",
  "roles/secretmanager.secretAccessor"
}
```