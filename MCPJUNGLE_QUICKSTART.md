# MCPJungle Gateway - Quick Start Guide

Get MCPJungle Gateway up and running in 5 minutes!

## Prerequisites

- Docker and Docker Compose installed
- Node.js 18+ (for MCP servers)
- (Optional) GitHub Personal Access Token
- (Optional) Notion Integration Token

## Step 1: Configure Environment

```bash
# Copy the example environment file
cp .env.mcpjungle.example .env.mcpjungle

# Edit the file and set your tokens (optional for testing)
# GITHUB_TOKEN=ghp_your_github_token_here
# NOTION_API_KEY=secret_your_notion_key_here
nano .env.mcpjungle
```

## Step 2: Start MCPJungle Gateway

```bash
# Build and start services (including Jaeger for tracing)
make mcpjungle

# Or manually with docker compose
docker compose up -d mcpjungle-gateway jaeger
```

Wait ~30 seconds for all services to initialize.

## Step 3: Verify Deployment

```bash
# Check health
make mcpjungle-health

# Or use curl
curl http://localhost:9100/health
```

Expected output:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000000",
  "services": {
    "max_serve": "healthy",
    "qdrant": "healthy",
    "redis": "healthy",
    "mcp_client": "healthy"
  }
}
```

## Step 4: Test MCP Endpoints

### List Available Servers

```bash
curl -H "Authorization: Bearer sk-test-key-123" \
  http://localhost:9100/mcp/servers
```

### Check Your Role & Permissions

```bash
curl -H "Authorization: Bearer sk-test-key-123" \
  http://localhost:9100/mcp/acl/role
```

### List GitHub Tools (Developer Role)

```bash
curl -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  -d '{"server_id": "mcp-github"}' \
  http://localhost:9100/mcp/tools/list
```

### Search GitHub Repositories

```bash
curl -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-github",
    "tool_name": "github_search_repositories",
    "arguments": {
      "query": "language:python stars:>1000",
      "per_page": 5
    }
  }' \
  http://localhost:9100/mcp/tools/call
```

## Step 5: Run Test Suite

```bash
# Run comprehensive tests
make mcpjungle-test

# Or manually
python test_mcpjungle.py
```

## Step 6: View Traces in Jaeger

```bash
# Open Jaeger UI
make jaeger-ui

# Or manually open
open http://localhost:16686
```

In Jaeger:
1. Select service: `mcpjungle-gateway`
2. Click "Find Traces"
3. Explore request traces with timing details

## Available API Keys & Roles

### Default API Keys

| API Key | Role | Permissions |
|---------|------|-------------|
| `sk-admin-key-456` | admin | Full access to all servers |
| `sk-dev-key-789` | developer | Read/write to GitHub, read-only to Notion |
| `sk-test-key-123` | analyst | Read-only access |

### Role Capabilities

**Admin**:
- All MCP servers: read/write/delete
- Rate limit: 1000 req/min

**Developer**:
- GitHub: Full access (read/write)
- Notion: Read-only
- Filesystem: Read/write
- Rate limit: 300 req/min

**Analyst**:
- All servers: Read-only
- Rate limit: 100 req/min

## Common Endpoints

### Gateway Endpoints

- **Health Check**: `GET http://localhost:9100/health`
- **Metrics**: `GET http://localhost:9100/metrics` (requires auth)
- **API Docs**: `http://localhost:9100/docs`

### MCP Endpoints

- **List Servers**: `GET /mcp/servers`
- **List Resources**: `POST /mcp/resources/list`
- **Read Resource**: `POST /mcp/resources/read`
- **List Tools**: `POST /mcp/tools/list`
- **Call Tool**: `POST /mcp/tools/call`
- **Get Role Info**: `GET /mcp/acl/role`

### Monitoring

- **Jaeger UI**: `http://localhost:16686`
- **Gateway Logs**: `make mcpjungle-logs`

## Example: Python Client

```python
import httpx
import asyncio

API_KEY = "sk-dev-key-789"
BASE_URL = "http://localhost:9100"

async def main():
    async with httpx.AsyncClient() as client:
        # List servers
        response = await client.get(
            f"{BASE_URL}/mcp/servers",
            headers={"Authorization": f"Bearer {API_KEY}"}
        )
        print("Servers:", response.json())
        
        # Search repositories
        response = await client.post(
            f"{BASE_URL}/mcp/tools/call",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "server_id": "mcp-github",
                "tool_name": "github_search_repositories",
                "arguments": {"query": "language:python", "per_page": 5}
            }
        )
        print("Results:", response.json())

asyncio.run(main())
```

## Troubleshooting

### Gateway Not Starting

```bash
# Check logs
make mcpjungle-logs

# Rebuild
make mcpjungle-build
make mcpjungle-start
```

### MCP Servers Not Connecting

**Issue**: Servers show as not connected

**Solution**:
1. Verify Node.js is installed in container:
   ```bash
   docker compose exec mcpjungle-gateway node --version
   ```
2. Check credentials are set (GITHUB_TOKEN, NOTION_API_KEY)
3. View detailed logs:
   ```bash
   docker compose logs mcpjungle-gateway | grep -i "mcp"
   ```

### Authentication Errors

**Issue**: 401 Unauthorized

**Solution**:
- Verify API key format: `Bearer sk-test-key-123`
- Check key is defined in docker-compose.yaml or .env

### Permission Denied

**Issue**: 403 Forbidden

**Solution**:
- Check your role: `GET /mcp/acl/role`
- Verify role has permission in `configs/mcp-acl.yaml`
- Ensure operation type matches permission (read vs write)

## Next Steps

1. **Customize Roles**: Edit `configs/mcp-acl.yaml`
2. **Add MCP Servers**: Edit `configs/mcp-servers.yaml`
3. **Configure Tokens**: Set GITHUB_TOKEN and NOTION_API_KEY
4. **Production Setup**: See `MCPJUNGLE_README.md`
5. **Integration**: Build agents using the MCP endpoints

## Stopping Services

```bash
# Stop MCPJungle gateway
make mcpjungle-stop

# Stop all services
docker compose down

# Clean up (removes volumes)
make clean
```

## Useful Commands

```bash
# View all logs
docker compose logs -f

# View specific service logs
docker compose logs -f mcpjungle-gateway
docker compose logs -f jaeger

# Restart gateway
docker compose restart mcpjungle-gateway

# Check all services
docker compose ps

# Access gateway shell
docker compose exec mcpjungle-gateway bash
```

## Support

- **Documentation**: See `MCPJUNGLE_README.md` for detailed documentation
- **API Docs**: Visit `http://localhost:9100/docs` for interactive API documentation
- **Traces**: Use Jaeger UI at `http://localhost:16686` for debugging

## Quick Reference

```bash
# Essential Commands
make mcpjungle           # Start everything
make mcpjungle-health    # Check health
make mcpjungle-test      # Run tests
make mcpjungle-logs      # View logs
make mcpjungle-stop      # Stop services
make jaeger-ui           # Open tracing UI

# Configuration Files
configs/mcp-servers.yaml # MCP server definitions
configs/mcp-acl.yaml     # Role-based access control
.env.mcpjungle          # Environment variables
```

---

**You're ready to use MCPJungle Gateway!** 🎉

Start building agents that leverage GitHub, Notion, and filesystem capabilities through the unified MCP interface.
