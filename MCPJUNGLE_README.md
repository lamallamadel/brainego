# MCPJungle Gateway - MCP-Enabled AI Platform

## Overview

MCPJungle Gateway is an enhanced AI platform gateway that integrates the Model Context Protocol (MCP) with authentication, OpenTelemetry tracing, and role-based access control (RBAC). It provides a unified interface to multiple MCP servers while maintaining security and observability.

## Features

### Core Capabilities

- **MCP Server Management**: Connect to multiple MCP servers (GitHub, Notion, Filesystem)
- **Authentication & Authorization**: API key-based authentication with role-based access control
- **OpenTelemetry Tracing**: Distributed tracing with Jaeger integration
- **Unified `/mcp` Endpoint**: Single endpoint for all MCP operations
- **ACL Configuration**: Fine-grained permissions for agents and users
- **Rate Limiting**: Per-role rate limits with Redis-backed tracking
- **Memory & RAG Integration**: Seamless integration with existing services

### Supported MCP Servers

1. **mcp-github**: GitHub repositories, issues, PRs, and code search
2. **mcp-notion**: Notion databases, pages, and blocks
3. **mcp-filesystem**: File system operations with sandboxing

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for MCP servers)
- GitHub Personal Access Token (optional, for GitHub MCP)
- Notion Integration Token (optional, for Notion MCP)

### Setup

1. **Configure Environment Variables**:
```bash
cp .env.mcpjungle.example .env.mcpjungle

# Edit .env.mcpjungle and set:
# - GITHUB_TOKEN (for GitHub MCP server)
# - NOTION_API_KEY (for Notion MCP server)
# - API_KEYS (customize your API keys)
```

2. **Configure MCP Servers** (optional):
Edit `configs/mcp-servers.yaml` to enable/disable servers or modify settings.

3. **Configure Access Control** (optional):
Edit `configs/mcp-acl.yaml` to customize roles and permissions.

4. **Start Services**:
```bash
# Start all services including MCPJungle Gateway
docker compose up -d mcpjungle-gateway

# Or start all services
docker compose up -d
```

5. **Verify Deployment**:
```bash
# Check health
curl http://localhost:9100/health

# Check available servers (requires API key)
curl -H "Authorization: Bearer sk-project-agent-key-321" http://localhost:9100/mcp/servers
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Client Layer                        │
│         (HTTP/REST with Bearer Token Auth)             │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│            MCPJungle Gateway (Port 9100)                │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Authentication & Authorization (ACL)           │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  OpenTelemetry Tracing (Jaeger)                │   │
│  └─────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────┐   │
│  │  MCP Client Manager                             │   │
│  │  - Connection Pooling                           │   │
│  │  - Request Routing                              │   │
│  │  - Error Handling                               │   │
│  └─────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────┘
                   │
         ┌─────────┴─────────┬─────────────┐
         │                   │             │
┌────────▼────────┐  ┌───────▼──────┐  ┌──▼──────────┐
│  MCP GitHub     │  │ MCP Notion   │  │ MCP         │
│  Server         │  │ Server       │  │ Filesystem  │
│  (npx)          │  │ (npx)        │  │ (npx)       │
└─────────────────┘  └──────────────┘  └─────────────┘
```

## API Reference

### Authentication

All MCP endpoints require authentication using Bearer tokens:

```bash
curl -H "Authorization: Bearer sk-test-key-123" <endpoint>
```

### Endpoints

#### POST `/mcp`
Unified MCP endpoint for core operations in CI/staging.

**Request (list tools)**:
```json
{
  "action": "list_tools",
  "server_id": "mcp-github"
}
```

**Request (call tool)**:
```json
{
  "action": "call_tool",
  "server_id": "mcp-github",
  "tool_name": "github_search_repositories",
  "arguments": {"query": "language:python stars:>1000"}
}
```

Supported actions: `list_tools`, `call_tool`, `list_resources`, `read_resource`.

#### GET `/mcp/servers`
List all available MCP servers (filtered by user role).

**Response**:
```json
{
  "servers": [
    {
      "id": "mcp-github",
      "name": "GitHub MCP Server",
      "description": "Access GitHub repositories, issues, PRs, and code",
      "connected": true,
      "capabilities": ["resources", "tools", "prompts"]
    }
  ],
  "total": 3,
  "role": "developer"
}
```

#### POST `/mcp/resources/list`
List resources from an MCP server.

**Request**:
```json
{
  "server_id": "mcp-github"
}
```

**Response**:
```json
{
  "server_id": "mcp-github",
  "resources": [
    {
      "uri": "github://repos/user/repo",
      "name": "repository",
      "description": "GitHub repository resource"
    }
  ],
  "count": 10
}
```

#### POST `/mcp/resources/read`
Read a specific resource.

**Request**:
```json
{
  "server_id": "mcp-github",
  "uri": "github://repos/octocat/hello-world"
}
```

#### POST `/mcp/tools/list`
List available tools from an MCP server.

**Request**:
```json
{
  "server_id": "mcp-github"
}
```

**Response**:
```json
{
  "server_id": "mcp-github",
  "tools": [
    {
      "name": "github_search_repositories",
      "description": "Search GitHub repositories",
      "inputSchema": {...}
    }
  ],
  "count": 8
}
```

#### POST `/mcp/tools/call`
Call a tool on an MCP server.

**Request**:
```json
{
  "server_id": "mcp-github",
  "tool_name": "github_search_repositories",
  "arguments": {
    "query": "language:python stars:>1000",
    "per_page": 10
  }
}
```

**Response**:
```json
{
  "server_id": "mcp-github",
  "tool_name": "github_search_repositories",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 10 repositories matching query..."
      }
    ],
    "isError": false
  }
}
```

#### GET `/mcp/acl/role`
Get ACL role information for authenticated user.

**Response**:
```json
{
  "role": "developer",
  "description": "Read/write access to code repositories and filesystem",
  "servers": ["mcp-github", "mcp-notion", "mcp-filesystem"],
  "rate_limits": {
    "requests_per_minute": 300,
    "requests_per_hour": 5000
  },
  "permissions": {
    "mcp-github": {
      "operations": ["read", "write"],
      "resources_count": 5,
      "tools_count": 9
    }
  }
}
```

## Role-Based Access Control

### Predefined Roles

#### Admin
- **Description**: Full access to all MCP servers and operations
- **Permissions**: All resources, tools, operations (read/write/delete)
- **Rate Limits**: 1000 req/min, 10000 req/hour

#### Project-Agent
- **Description**: Scoped read-only access for project automation agents
- **Permissions**: Read-only GitHub + Notion tools for test repositories/workspaces
- **Rate Limits**: 120 req/min, 1800 req/hour

#### Developer
- **Description**: Read/write access to code repositories and filesystem
- **Permissions**:
  - GitHub: All resources and tools (read/write)
  - Notion: Read-only access
  - Filesystem: Read/write access
- **Rate Limits**: 300 req/min, 5000 req/hour

#### Analyst
- **Description**: Read-only access to data sources
- **Permissions**:
  - GitHub: Repository browsing, issue viewing (read)
  - Notion: Database and page reading (read)
  - Filesystem: File reading and listing (read)
- **Rate Limits**: 100 req/min, 2000 req/hour

#### Writer
- **Description**: Write access to Notion and limited GitHub access
- **Permissions**:
  - GitHub: Issue management (read/write)
  - Notion: Full access (read/write)
  - Filesystem: File read/write
- **Rate Limits**: 200 req/min, 3000 req/hour

#### Readonly (Default)
- **Description**: Read-only access to all sources
- **Permissions**: Read-only across all servers
- **Rate Limits**: 60 req/min, 1000 req/hour

### Customizing Roles

Edit `configs/mcp-acl.yaml` to customize roles and permissions:

```yaml
roles:
  custom_role:
    description: "Custom role description"
    permissions:
      mcp-github:
        resources:
          - "repositories"
          - "issues"
        tools:
          - "github_search_repositories"
          - "github_list_issues"
        operations: ["read"]
    rate_limits:
      requests_per_minute: 120
      requests_per_hour: 2000
```

## OpenTelemetry Tracing

### Jaeger UI

Access the Jaeger UI to view distributed traces:

```
http://localhost:16686
```

### Trace Information

Traces include:
- Request authentication and authorization
- MCP server connection establishment
- Tool/resource invocations
- Response times and errors

### Example Trace Flow

```
mcpjungle-gateway: POST /mcp/tools/call
  ├─ verify_api_key (100ms)
  ├─ validate_acl_permissions (50ms)
  ├─ call_mcp_tool (1200ms)
  │   ├─ connect_to_server (200ms)
  │   ├─ call_tool (900ms)
  │   └─ parse_response (100ms)
  └─ format_response (50ms)
Total: 1400ms
```

## Configuration Files

### `configs/mcp-servers.yaml`

Defines MCP servers and their connection parameters:

```yaml
servers:
  mcp-github:
    name: "GitHub MCP Server"
    type: "stdio"
    command: "npx"
    args:
      - "-y"
      - "@modelcontextprotocol/server-github"
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"
    enabled: true
    timeout: 30
```

### `configs/mcp-acl.yaml`

Defines roles, permissions, and rate limits:

```yaml
roles:
  developer:
    description: "Read/write access to code repositories"
    permissions:
      mcp-github:
        resources: ["repositories", "issues", "pull_requests"]
        tools: ["github_search_repositories", "github_create_issue"]
        operations: ["read", "write"]
    rate_limits:
      requests_per_minute: 300
      requests_per_hour: 5000

api_key_roles:
  sk-dev-key-789: developer
```

## Example Usage

### Python Client Example

```python
import httpx

API_KEY = "sk-dev-key-789"
BASE_URL = "http://localhost:9100"
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

async def main():
    async with httpx.AsyncClient() as client:
        # List available servers
        response = await client.get(
            f"{BASE_URL}/mcp/servers",
            headers=HEADERS
        )
        print("Servers:", response.json())
        
        # Search GitHub repositories
        response = await client.post(
            f"{BASE_URL}/mcp/tools/call",
            headers=HEADERS,
            json={
                "server_id": "mcp-github",
                "tool_name": "github_search_repositories",
                "arguments": {
                    "query": "language:python",
                    "per_page": 5
                }
            }
        )
        print("Search Results:", response.json())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### cURL Examples

```bash
# List MCP servers
curl -H "Authorization: Bearer sk-test-key-123" \
  http://localhost:9100/mcp/servers

# List GitHub tools
curl -X POST \
  -H "Authorization: Bearer sk-test-key-123" \
  -H "Content-Type: application/json" \
  -d '{"server_id": "mcp-github"}' \
  http://localhost:9100/mcp/tools/list

# Search repositories
curl -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-github",
    "tool_name": "github_search_repositories",
    "arguments": {
      "query": "language:python stars:>1000",
      "per_page": 10
    }
  }' \
  http://localhost:9100/mcp/tools/call

# Read a file (filesystem MCP)
curl -X POST \
  -H "Authorization: Bearer sk-dev-key-789" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-filesystem",
    "tool_name": "read_file",
    "arguments": {
      "path": "/workspace/example.txt"
    }
  }' \
  http://localhost:9100/mcp/tools/call
```

## Security Best Practices

1. **API Keys**: 
   - Use strong, randomly generated API keys
   - Rotate keys regularly
   - Store keys in secrets manager (not .env files) in production

2. **MCP Server Credentials**:
   - Use tokens with minimal required permissions
   - Rotate GitHub/Notion tokens regularly
   - Use separate tokens for different environments

3. **Network Security**:
   - Deploy behind HTTPS reverse proxy
   - Use firewall rules to restrict access
   - Enable CORS only for trusted origins

4. **Rate Limiting**:
   - Enable rate limiting in production
   - Monitor for abuse patterns
   - Adjust limits based on usage patterns

5. **Filesystem Security**:
   - Configure `allowed_paths` in mcp-servers.yaml
   - Block sensitive directories (.git, .env)
   - Set appropriate `max_file_size_mb` limits

## Monitoring & Debugging

### Logs

```bash
# View gateway logs
docker compose logs -f mcpjungle-gateway

# View Jaeger logs
docker compose logs -f jaeger
```

### Metrics

```bash
# Get performance metrics (public in CI/staging)
curl http://localhost:9100/metrics
```

Example response fields include `mcp_requests`, `mcp_errors`, and `mcp_error_rate`.

### Health Checks

```bash
# Check gateway health
curl http://localhost:9100/health
```

## Troubleshooting

### MCP Server Not Connecting

**Issue**: Server shows as not connected
**Solutions**:
1. Check Node.js is installed: `docker compose exec mcpjungle-gateway node --version`
2. Verify credentials (GITHUB_TOKEN, NOTION_API_KEY) are set
3. Check server logs for connection errors
4. Ensure npx can reach npm registry

### Authentication Errors

**Issue**: 401 Unauthorized errors
**Solutions**:
1. Verify API key is correct
2. Check Authorization header format: `Bearer <key>`
3. Ensure API key is defined in .env.mcpjungle

### Permission Denied Errors

**Issue**: 403 Forbidden errors
**Solutions**:
1. Check user role: `GET /mcp/acl/role`
2. Verify role has required permissions in mcp-acl.yaml
3. Check rate limits haven't been exceeded

### Tracing Not Working

**Issue**: No traces appearing in Jaeger
**Solutions**:
1. Verify `ENABLE_TELEMETRY=true`
2. Check Jaeger is running: `docker compose ps jaeger`
3. Verify OTLP_ENDPOINT is correct
4. Check network connectivity between services

## Development

### Local Development Setup

```bash
# Install dependencies
pip install -r requirements.txt
npm install -g @modelcontextprotocol/server-github
npm install -g @modelcontextprotocol/server-notion
npm install -g @modelcontextprotocol/server-filesystem

# Set environment variables
export MAX_SERVE_URL=http://localhost:8080
export QDRANT_HOST=localhost
export REDIS_HOST=localhost
export GITHUB_TOKEN=your_token
export NOTION_API_KEY=your_key

# Run gateway
python gateway_service_mcp.py
```

### Testing

```bash
# Run health check
curl http://localhost:9100/health

# Test MCP endpoints
python test_mcpjungle.py
```

## Contributing

When adding new MCP servers:

1. Add server configuration to `configs/mcp-servers.yaml`
2. Define permissions in `configs/mcp-acl.yaml`
3. Update documentation
4. Test with different roles
5. Add example usage

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [Your Repo URL]
- Documentation: [Your Docs URL]
- Slack/Discord: [Your Community URL]

---

**Built with**: FastAPI, MCP SDK, OpenTelemetry, Redis, Qdrant, Jaeger
