# MCP Integration Quick Start Guide

Get up and running with MCP application server integrations in minutes.

## Prerequisites

- MCPJungle Gateway running (see main README.md)
- Node.js and npm installed (for MCP servers)
- Credentials for the services you want to integrate

## Quick Setup

### 1. Configure Environment Variables

Copy the example environment file:

```bash
cp .env.mcpjungle.example .env.mcpjungle
```

### 2. Set Up Service Credentials

Choose which services you want to integrate:

#### GitHub (Easiest)

1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Select scopes: `repo`, `read:org`, `read:user`
4. Copy token and add to `.env.mcpjungle`:

```bash
GITHUB_TOKEN=ghp_your_token_here
```

#### Notion (Easy)

1. Go to https://www.notion.so/my-integrations
2. Create new integration
3. Copy "Internal Integration Token"
4. Share pages/databases with the integration
5. Add to `.env.mcpjungle`:

```bash
NOTION_API_KEY=secret_your_token_here
```

#### Slack (Medium)

1. Go to https://api.slack.com/apps
2. Create new app or select existing
3. Add OAuth scopes: `channels:read`, `channels:history`, `chat:write`, `users:read`
4. Install app to workspace
5. Copy "Bot User OAuth Token"
6. Add to `.env.mcpjungle`:

```bash
SLACK_BOT_TOKEN=xoxb-your-token-here
```

#### Gmail (Advanced - Requires OAuth 2.0)

Use the helper script:

```bash
python setup_google_oauth.py --service gmail
```

Follow the prompts to:
1. Set up Google Cloud project
2. Enable Gmail API
3. Create OAuth credentials
4. Get refresh token

Add the output to `.env.mcpjungle`.

#### Google Calendar (Advanced - Requires OAuth 2.0)

Use the helper script:

```bash
python setup_google_oauth.py --service calendar
```

Follow the prompts and add the output to `.env.mcpjungle`.

### 3. Start the Gateway

```bash
# Using Docker Compose
docker compose up -d gateway

# Or using the start script
./start_gateway.sh
```

### 4. Run Integration Tests

Test your configuration:

```bash
python test_mcp_integrations.py
```

Expected output:
```
======================================================================
          MCP Application Servers - Integration Test Suite          
======================================================================

✓ Gateway is healthy
✓ GitHub MCP Server
✓ Notion MCP Server
✓ Slack MCP Server
✓ Gmail MCP Server
✓ Calendar MCP Server

All integration tests passed! (5/5)
```

## Basic Usage Examples

### List Available Servers

```bash
curl -X GET http://localhost:9100/mcp/servers \
  -H "Authorization: Bearer sk-admin-key-456"
```

### Search GitHub Repositories

```bash
curl -X POST http://localhost:9100/mcp/tools/call \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-github",
    "tool_name": "github_search_repositories",
    "arguments": {
      "query": "language:python stars:>1000",
      "per_page": 5
    }
  }'
```

### Search Notion Pages

```bash
curl -X POST http://localhost:9100/mcp/tools/call \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-notion",
    "tool_name": "notion_search",
    "arguments": {
      "query": "meeting notes",
      "page_size": 10
    }
  }'
```

### List Slack Channels

```bash
curl -X POST http://localhost:9100/mcp/tools/call \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-slack",
    "tool_name": "slack_list_channels",
    "arguments": {
      "limit": 20
    }
  }'
```

### Search Gmail Messages

```bash
curl -X POST http://localhost:9100/mcp/tools/call \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-gmail",
    "tool_name": "gmail_search_messages",
    "arguments": {
      "query": "is:unread",
      "max_results": 10
    }
  }'
```

### List Calendar Events

```bash
curl -X POST http://localhost:9100/mcp/tools/call \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-calendar",
    "tool_name": "calendar_list_events",
    "arguments": {
      "calendar_id": "primary",
      "time_min": "2024-01-01T00:00:00Z",
      "time_max": "2024-12-31T23:59:59Z",
      "max_results": 10
    }
  }'
```

## Python Client Example

```python
import httpx
import asyncio

async def search_github():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:9100/mcp/tools/call",
            headers={"Authorization": "Bearer sk-admin-key-456"},
            json={
                "server_id": "mcp-github",
                "tool_name": "github_search_repositories",
                "arguments": {
                    "query": "machine learning",
                    "per_page": 5
                }
            }
        )
        print(response.json())

asyncio.run(search_github())
```

## Troubleshooting

### Server Not Available

Check if server is enabled in `configs/mcp-servers.yaml`:

```yaml
mcp-github:
  enabled: true
```

### Authentication Errors

**GitHub**: Test token with:
```bash
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user
```

**Notion**: Verify integration has access to your pages

**Slack**: Check bot is installed and has required scopes

**Gmail/Calendar**: Verify OAuth tokens haven't expired

### No Refresh Token (Google Services)

If `setup_google_oauth.py` doesn't return a refresh token:

1. Go to https://myaccount.google.com/permissions
2. Remove access for your app
3. Run the setup script again

### Connection Timeouts

Increase timeout in `configs/mcp-servers.yaml`:

```yaml
settings:
  default_timeout: 60  # Increase from 30
```

## Next Steps

1. **Configure Access Control**: Edit `configs/mcp-acl.yaml` for role-based permissions
2. **Enable Caching**: Reduce API calls by enabling caching
3. **Monitor Performance**: Use `/metrics` endpoint to track usage
4. **Review Documentation**: See `MCP_INTEGRATIONS.md` for detailed info

## Security Checklist

- [ ] Changed default API keys in `.env.mcpjungle`
- [ ] Set minimum required scopes for each service
- [ ] Configured role-based access control
- [ ] Never committed `.env.mcpjungle` to git
- [ ] Enabled HTTPS for production
- [ ] Set up rate limiting
- [ ] Regular credential rotation

## Getting Help

- Check gateway logs: `docker compose logs -f gateway`
- Run health check: `curl http://localhost:9100/health`
- Review full documentation: `MCP_INTEGRATIONS.md`
- Test configuration: `python test_mcp_integrations.py`

## Common Issues

**"Server not found"**: Server not configured in `mcp-servers.yaml`

**"Authentication failed"**: Invalid or expired credentials

**"Permission denied"**: Check ACL configuration in `mcp-acl.yaml`

**"Tool not found"**: List available tools with `/mcp/tools/list`

**"Rate limit exceeded"**: Adjust rate limits in ACL configuration
