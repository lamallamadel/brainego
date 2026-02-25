# MCP Application Server Integrations

This document describes the configuration and setup for MCP (Model Context Protocol) application server integrations.

## Overview

The MCPJungle Gateway supports integration with multiple MCP application servers, providing seamless access to external services like GitHub, Notion, Slack, Gmail, and Google Calendar through a unified API.

## Supported MCP Servers

### 1. GitHub MCP Server (`mcp-github`)

**Purpose**: Access GitHub repositories, issues, pull requests, and code search.

**Authentication**: Personal Access Token (PAT)

**Required Scopes**:
- `repo` - Full repository access
- `read:org` - Read organization data
- `read:user` - Read user profile data

**Configuration**:
```yaml
mcp-github:
  name: "GitHub MCP Server"
  type: "stdio"
  command: "npx"
  args:
    - "-y"
    - "@modelcontextprotocol/server-github"
  env:
    GITHUB_TOKEN: "${GITHUB_TOKEN}"
```

**Environment Variables**:
```bash
GITHUB_TOKEN=ghp_your_personal_access_token_here
```

**Available Tools**:
- `github_search_repositories` - Search for repositories
- `github_get_repository` - Get repository details
- `github_list_issues` - List issues in a repository
- `github_create_issue` - Create a new issue
- `github_get_issue` - Get issue details
- `github_list_pull_requests` - List pull requests
- `github_get_pull_request` - Get pull request details
- `github_search_code` - Search code across repositories
- `github_get_file_contents` - Get file contents from a repository

**Resources**:
- `repositories` - Repository data
- `issues` - Issue tracking
- `pull_requests` - PR management
- `commits` - Commit history
- `code_search` - Code search results

### 2. Notion MCP Server (`mcp-notion`)

**Purpose**: Access and manage Notion pages, databases, and blocks.

**Authentication**: OAuth Integration Token

**Configuration**:
```yaml
mcp-notion:
  name: "Notion MCP Server"
  type: "stdio"
  command: "npx"
  args:
    - "-y"
    - "@modelcontextprotocol/server-notion"
  env:
    NOTION_API_KEY: "${NOTION_API_KEY}"
```

**Environment Variables**:
```bash
NOTION_API_KEY=secret_your_notion_integration_token
```

**Setup Steps**:
1. Go to https://www.notion.so/my-integrations
2. Create a new integration
3. Copy the "Internal Integration Token"
4. Share pages/databases with the integration

**Available Tools**:
- `notion_search` - Search across workspace
- `notion_get_page` - Get page details
- `notion_create_page` - Create a new page
- `notion_update_page` - Update page properties
- `notion_get_database` - Get database schema
- `notion_query_database` - Query database entries
- `notion_get_block_children` - Get block contents
- `notion_append_block_children` - Add blocks to a page

**Resources**:
- `databases` - Database schemas and queries
- `pages` - Page content and metadata
- `blocks` - Block-level content

### 3. Slack MCP Server (`mcp-slack`)

**Purpose**: Access Slack channels, messages, and workspace data.

**Authentication**: Bot Token

**Required Scopes**:
- `channels:read` - View channels
- `channels:history` - Read message history
- `chat:write` - Send messages
- `users:read` - View user information
- `search:read` - Search messages (if using search)
- `files:write` - Upload files (if using file upload)
- `reactions:write` - Add reactions (if using reactions)

**Configuration**:
```yaml
mcp-slack:
  name: "Slack MCP Server"
  type: "stdio"
  command: "npx"
  args:
    - "-y"
    - "@modelcontextprotocol/server-slack"
  env:
    SLACK_BOT_TOKEN: "${SLACK_BOT_TOKEN}"
```

**Environment Variables**:
```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
```

**Setup Steps**:
1. Go to https://api.slack.com/apps
2. Create a new app or select existing
3. Add required OAuth scopes under "OAuth & Permissions"
4. Install app to workspace
5. Copy "Bot User OAuth Token"

**Available Tools**:
- `slack_list_channels` - List workspace channels
- `slack_get_channel_history` - Get channel message history
- `slack_post_message` - Send a message to a channel
- `slack_search_messages` - Search messages across workspace
- `slack_list_users` - List workspace users
- `slack_get_user_info` - Get user details
- `slack_upload_file` - Upload a file
- `slack_add_reaction` - Add emoji reaction to a message

**Resources**:
- `channels` - Channel information
- `messages` - Message data
- `users` - User profiles

### 4. Gmail MCP Server (`mcp-gmail`)

**Purpose**: Read-only access to Gmail messages and threads.

**Authentication**: OAuth 2.0 (Client ID, Client Secret, Refresh Token)

**Configuration**:
```yaml
mcp-gmail:
  name: "Gmail MCP Server"
  type: "stdio"
  command: "npx"
  args:
    - "-y"
    - "@modelcontextprotocol/server-gmail"
  env:
    GMAIL_CLIENT_ID: "${GMAIL_CLIENT_ID}"
    GMAIL_CLIENT_SECRET: "${GMAIL_CLIENT_SECRET}"
    GMAIL_REFRESH_TOKEN: "${GMAIL_REFRESH_TOKEN}"
  security:
    read_only: true
    allowed_operations:
      - "read"
      - "search"
      - "list"
```

**Environment Variables**:
```bash
GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your-client-secret
GMAIL_REFRESH_TOKEN=your-refresh-token
```

**Setup Steps**:
1. Go to Google Cloud Console: https://console.cloud.google.com/
2. Create a project or select existing
3. Enable Gmail API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download credentials JSON
6. Use OAuth 2.0 Playground or custom script to get refresh token:
   - Go to https://developers.google.com/oauthplayground/
   - Click settings (gear icon), check "Use your own OAuth credentials"
   - Enter Client ID and Client Secret
   - Select Gmail API v1 scopes (at least `gmail.readonly`)
   - Authorize and exchange authorization code for tokens

**Required Scopes**:
- `https://www.googleapis.com/auth/gmail.readonly` - Read-only access

**Available Tools**:
- `gmail_list_messages` - List messages
- `gmail_get_message` - Get message details
- `gmail_search_messages` - Search messages
- `gmail_get_thread` - Get thread details
- `gmail_list_labels` - List labels
- `gmail_get_profile` - Get user profile

**Resources**:
- `messages` - Email messages
- `threads` - Email threads
- `labels` - Gmail labels

**Security Notes**:
- Server is configured as **read-only**
- No write operations are permitted
- Only search, list, and read operations allowed

### 5. Google Calendar MCP Server (`mcp-calendar`)

**Purpose**: Access and manage Google Calendar events and calendars.

**Authentication**: OAuth 2.0 (Client ID, Client Secret, Refresh Token)

**Configuration**:
```yaml
mcp-calendar:
  name: "Google Calendar MCP Server"
  type: "stdio"
  command: "npx"
  args:
    - "-y"
    - "@modelcontextprotocol/server-google-calendar"
  env:
    GOOGLE_CALENDAR_CLIENT_ID: "${GOOGLE_CALENDAR_CLIENT_ID}"
    GOOGLE_CALENDAR_CLIENT_SECRET: "${GOOGLE_CALENDAR_CLIENT_SECRET}"
    GOOGLE_CALENDAR_REFRESH_TOKEN: "${GOOGLE_CALENDAR_REFRESH_TOKEN}"
```

**Environment Variables**:
```bash
GOOGLE_CALENDAR_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=your-client-secret
GOOGLE_CALENDAR_REFRESH_TOKEN=your-refresh-token
```

**Setup Steps**:
1. Go to Google Cloud Console: https://console.cloud.google.com/
2. Create a project or select existing
3. Enable Google Calendar API
4. Create OAuth 2.0 credentials (Desktop app)
5. Download credentials JSON
6. Use OAuth 2.0 Playground to get refresh token:
   - Go to https://developers.google.com/oauthplayground/
   - Click settings, check "Use your own OAuth credentials"
   - Enter Client ID and Client Secret
   - Select Calendar API v3 scopes
   - Authorize and exchange authorization code for tokens

**Required Scopes**:
- `https://www.googleapis.com/auth/calendar` - Full calendar access
- `https://www.googleapis.com/auth/calendar.readonly` - Read-only (alternative)

**Available Tools**:
- `calendar_list_calendars` - List user's calendars
- `calendar_get_calendar` - Get calendar details
- `calendar_list_events` - List events in a calendar
- `calendar_get_event` - Get event details
- `calendar_create_event` - Create a new event
- `calendar_update_event` - Update an event
- `calendar_delete_event` - Delete an event
- `calendar_search_events` - Search events

**Resources**:
- `calendars` - Calendar list and metadata
- `events` - Calendar events

## Testing

### Running Integration Tests

All MCP servers have comprehensive integration tests in `test_mcp_integrations.py`:

```bash
# Run all integration tests
python test_mcp_integrations.py

# Set custom gateway URL and API key
GATEWAY_URL=http://localhost:9100 TEST_API_KEY=sk-admin-key-456 python test_mcp_integrations.py
```

### Test Coverage

Each server test suite includes:

1. **Server Availability**: Verify server is configured and enabled
2. **Tool Listing**: List all available tools
3. **Basic Operations**: Test core functionality (search, list, read)
4. **Error Handling**: Verify proper error responses
5. **Resource Access**: Test resource listing and retrieval
6. **Authentication**: Verify credentials are working

### Expected Output

```
======================================================================
          MCP Application Servers - Integration Test Suite          
======================================================================

ℹ Gateway URL: http://localhost:9100
ℹ Using API Key: sk-admin-key-456...

======================================================================
                        Gateway Health Check                         
======================================================================

✓ Gateway is healthy
✓   mcp: healthy
✓   rag: healthy

======================================================================
              GitHub MCP Server Integration Tests                    
======================================================================

✓ GitHub MCP server is available

----------------------------------------------------------------------
Test 1: List GitHub Tools
----------------------------------------------------------------------
✓ Retrieved 9 GitHub tools
  • github_search_repositories: Search for repositories on GitHub
  • github_get_repository: Get details about a specific repository
  ...

[Additional test output...]

======================================================================
                    Integration Test Summary                          
======================================================================

✓ GitHub MCP Server
✓ Notion MCP Server
✓ Slack MCP Server
✓ Gmail MCP Server
✓ Calendar MCP Server

======================================================================
All integration tests passed! (5/5)
======================================================================
```

## Configuration Files

### Main Configuration: `configs/mcp-servers.yaml`

Contains all MCP server definitions with:
- Connection parameters (command, args)
- Environment variables
- Capabilities (resources, tools, prompts)
- Security settings
- Timeout and retry configuration

### Environment File: `.env.mcpjungle`

Copy from `.env.mcpjungle.example` and configure:

```bash
# Copy example file
cp .env.mcpjungle.example .env.mcpjungle

# Edit with your credentials
nano .env.mcpjungle
```

Required variables:
- `GITHUB_TOKEN` - For GitHub access
- `NOTION_API_KEY` - For Notion access
- `SLACK_BOT_TOKEN` - For Slack access
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` - For Gmail
- `GOOGLE_CALENDAR_CLIENT_ID`, `GOOGLE_CALENDAR_CLIENT_SECRET`, `GOOGLE_CALENDAR_REFRESH_TOKEN` - For Calendar

## API Usage

### Listing Available Servers

```bash
curl -X GET http://localhost:9100/mcp/servers \
  -H "Authorization: Bearer sk-admin-key-456"
```

### Listing Tools from a Server

```bash
curl -X POST http://localhost:9100/mcp/tools/list \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{"server_id": "mcp-github"}'
```

### Calling a Tool

```bash
# Search GitHub repositories
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

### Listing Resources

```bash
curl -X POST http://localhost:9100/mcp/resources/list \
  -H "Authorization: Bearer sk-admin-key-456" \
  -H "Content-Type: application/json" \
  -d '{"server_id": "mcp-notion"}'
```

## Security Considerations

### API Key Management

- Store API keys in `.env.mcpjungle` file
- Never commit credentials to version control
- Use different keys for different environments
- Rotate keys regularly

### Access Control

Configure role-based access in `configs/mcp-acl.yaml`:

```yaml
roles:
  admin:
    servers:
      - mcp-github
      - mcp-notion
      - mcp-slack
      - mcp-gmail
      - mcp-calendar
    permissions:
      all: ["read", "write", "delete"]

  developer:
    servers:
      - mcp-github
      - mcp-slack
    permissions:
      mcp-github: ["read", "write"]
      mcp-slack: ["read"]

  analyst:
    servers:
      - mcp-github
      - mcp-gmail
    permissions:
      all: ["read"]
```

### Read-Only Mode

Gmail is configured as **read-only** by default:

```yaml
mcp-gmail:
  security:
    read_only: true
    allowed_operations:
      - "read"
      - "search"
      - "list"
```

### Rate Limiting

Configure rate limits per role:

```yaml
roles:
  developer:
    rate_limits:
      requests_per_minute: 60
      requests_per_hour: 1000
```

## Troubleshooting

### Server Not Connecting

1. Check if server is enabled in `configs/mcp-servers.yaml`
2. Verify credentials in `.env.mcpjungle`
3. Check gateway logs: `docker compose logs -f gateway`
4. Test authentication with provider (GitHub, Google, etc.)

### Authentication Failures

**GitHub**:
- Verify token has required scopes
- Check token hasn't expired
- Test with: `curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user`

**Notion**:
- Verify integration has access to pages/databases
- Check token format (should start with `secret_`)

**Slack**:
- Verify bot token format (should start with `xoxb-`)
- Check app is installed in workspace
- Verify required scopes are granted

**Gmail/Calendar**:
- Check OAuth tokens haven't expired
- Verify Client ID and Secret are correct
- Test token refresh
- Ensure APIs are enabled in Google Cloud Console

### Tool Call Failures

1. Check tool exists: List tools for the server
2. Verify arguments match tool schema
3. Check ACL permissions for your role
4. Review gateway logs for detailed errors

### Performance Issues

1. Check network latency to external services
2. Increase timeout in `mcp-servers.yaml`
3. Enable caching in global settings
4. Monitor with metrics endpoint: `/metrics`

## Best Practices

### Credential Management

- Use environment variables, never hardcode
- Store sensitive values in secrets manager (production)
- Different credentials per environment
- Minimum required scopes/permissions

### Error Handling

- Always check `isError` field in responses
- Implement retries for transient failures
- Log errors with context
- Monitor error rates

### Performance

- Enable caching for frequently accessed data
- Use pagination for large result sets
- Batch operations when possible
- Set appropriate timeouts

### Monitoring

- Track request latency and errors
- Monitor authentication failures
- Set up alerts for high error rates
- Review audit logs regularly

## Additional Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [GitHub API Documentation](https://docs.github.com/en/rest)
- [Notion API Documentation](https://developers.notion.com/)
- [Slack API Documentation](https://api.slack.com/)
- [Gmail API Documentation](https://developers.google.com/gmail/api)
- [Google Calendar API Documentation](https://developers.google.com/calendar/api)

## Support

For issues or questions:
1. Check gateway logs: `docker compose logs gateway`
2. Run integration tests: `python test_mcp_integrations.py`
3. Review configuration files
4. Check external service status pages
