# MCP Integration Tests

This document describes how to run and interpret the MCP application server integration tests.

## Overview

`test_mcp_integrations.py` provides comprehensive integration testing for all configured MCP servers:
- GitHub
- Notion
- Slack
- Gmail
- Google Calendar

## Prerequisites

1. **Gateway Running**: MCPJungle Gateway must be running on port 9100
2. **Credentials Configured**: Environment variables set in `.env.mcpjungle`
3. **Node.js/npm**: Required for MCP server packages

## Quick Start

```bash
# Run all integration tests
python test_mcp_integrations.py

# With custom settings
GATEWAY_URL=http://localhost:9100 TEST_API_KEY=sk-admin-key-456 python test_mcp_integrations.py
```

## What Gets Tested

### For Each MCP Server

1. **Server Availability**
   - Checks if server is registered and enabled
   - Verifies connection can be established

2. **Tool Listing**
   - Lists all available tools from the server
   - Validates tool metadata (name, description, schema)

3. **Basic Operations**
   - Executes representative operations for each service
   - Tests search, list, and read functionality
   - Verifies response format

4. **Resource Access**
   - Lists available resources
   - Tests resource retrieval

5. **Error Handling**
   - Validates proper error responses
   - Tests authentication failures
   - Checks timeout handling

### GitHub Tests (6 tests)

- ✓ List GitHub tools
- ✓ Search repositories
- ✓ Get repository details
- ✓ List repository issues
- ✓ Search code
- ✓ List resources

### Notion Tests (3 tests)

- ✓ List Notion tools
- ✓ Search Notion pages/databases
- ✓ List resources

### Slack Tests (5 tests)

- ✓ List Slack tools
- ✓ List channels
- ✓ List users
- ✓ Search messages
- ✓ List resources

### Gmail Tests (7 tests)

- ✓ List Gmail tools
- ✓ Get user profile
- ✓ List labels
- ✓ List messages
- ✓ Search messages
- ✓ Verify read-only enforcement
- ✓ List resources

### Calendar Tests (5 tests)

- ✓ List Calendar tools
- ✓ List calendars
- ✓ List events (with time range)
- ✓ Search events
- ✓ List resources

## Test Output

### Successful Run

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
  • github_list_issues: List issues in a repository
  • github_create_issue: Create a new issue in a repository
  • github_get_issue: Get details about a specific issue

----------------------------------------------------------------------
Test 2: Search GitHub Repositories
----------------------------------------------------------------------
✓ Successfully searched GitHub repositories
ℹ Found repositories in search results

[... more test output ...]

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

### Failed Test

```
======================================================================
              Slack MCP Server Integration Tests                     
======================================================================

✗ Slack MCP server is not available

ℹ Note: Some servers may require valid credentials to pass all tests
ℹ Check .env.mcpjungle file for required environment variables
```

## Exit Codes

- `0`: All tests passed
- `1`: Some tests failed

Perfect for CI/CD integration:

```bash
python test_mcp_integrations.py
if [ $? -eq 0 ]; then
  echo "All tests passed!"
else
  echo "Some tests failed!"
  exit 1
fi
```

## Configuration

### Environment Variables

Set these before running tests:

```bash
# Gateway settings
export GATEWAY_URL=http://localhost:9100
export TEST_API_KEY=sk-admin-key-456

# Or use defaults (shown above)
python test_mcp_integrations.py
```

### Credentials Required

Each server requires credentials in `.env.mcpjungle`:

**GitHub**:
```bash
GITHUB_TOKEN=ghp_xxx
```

**Notion**:
```bash
NOTION_API_KEY=secret_xxx
```

**Slack**:
```bash
SLACK_BOT_TOKEN=xoxb-xxx
```

**Gmail**:
```bash
GMAIL_CLIENT_ID=xxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=xxx
GMAIL_REFRESH_TOKEN=xxx
```

**Calendar**:
```bash
GOOGLE_CALENDAR_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CALENDAR_CLIENT_SECRET=xxx
GOOGLE_CALENDAR_REFRESH_TOKEN=xxx
```

## Test Behavior

### Partial Success

Tests are designed to allow partial success:

- If one server fails, other servers are still tested
- Each server test suite is independent
- Final summary shows which servers passed/failed

### Read-Only Testing

Tests are **read-only** by default:

- No data is created or modified
- Safe to run against production credentials
- Only uses search, list, and read operations

**Exception**: Tests don't actually create GitHub issues, calendar events, etc. They only verify the tools exist.

## Troubleshooting

### Gateway Not Running

```
✗ Cannot connect to gateway: Connection refused
ℹ Start the gateway with: docker compose up -d gateway
```

**Solution**: Start the gateway service

```bash
docker compose up -d gateway
```

### Authentication Failed

```
✗ Failed to list tools: 401
```

**Solution**: Check credentials in `.env.mcpjungle`

### Server Disabled

```
⚠ Server mcp-slack is disabled
```

**Solution**: Enable in `configs/mcp-servers.yaml`

```yaml
mcp-slack:
  enabled: true
```

### Missing Credentials

```
⚠ Gmail search failed or returned no results
```

**Solution**: Add credentials to `.env.mcpjungle` or use setup script:

```bash
python setup_google_oauth.py --service gmail
```

### Timeout Errors

```
✗ Error calling tool: Timeout
```

**Solution**: Increase timeout in `configs/mcp-servers.yaml`:

```yaml
settings:
  default_timeout: 60  # Increase from 30
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: MCP Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: pip install -r requirements.txt
    
    - name: Start Gateway
      run: docker compose up -d gateway
    
    - name: Wait for Gateway
      run: sleep 10
    
    - name: Run MCP Integration Tests
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        NOTION_API_KEY: ${{ secrets.NOTION_API_KEY }}
      run: python test_mcp_integrations.py
```

### GitLab CI Example

```yaml
mcp_integration_tests:
  stage: test
  image: python:3.9
  services:
    - docker:dind
  script:
    - pip install -r requirements.txt
    - docker compose up -d gateway
    - sleep 10
    - python test_mcp_integrations.py
  variables:
    GITHUB_TOKEN: $GITHUB_TOKEN
    NOTION_API_KEY: $NOTION_API_KEY
```

## Development

### Adding New Tests

To add tests for a new server:

1. Add server configuration to `configs/mcp-servers.yaml`
2. Add credentials to `.env.mcpjungle.example`
3. Create test class in `test_mcp_integrations.py`:

```python
class NewServerIntegrationTest(MCPIntegrationTest):
    async def run_tests(self) -> bool:
        print_header("New Server Integration Tests")
        
        server_id = "mcp-newserver"
        
        if not await self.check_server_available(server_id):
            return False
        
        # Add specific tests here
        
        return True
```

4. Add to test suite:

```python
newserver_test = NewServerIntegrationTest(client)
newserver_passed = await newserver_test.run_tests()
test_results.append(("NewServer", newserver_passed))
```

### Running Individual Tests

You can modify the script to run tests for specific servers:

```python
# Only test GitHub
github_test = GitHubIntegrationTest(client)
github_passed = await github_test.run_tests()
```

## Best Practices

1. **Run Before Commits**: Test changes before committing
2. **Regular Execution**: Run tests regularly to catch issues
3. **Monitor Credentials**: Rotate credentials if tests fail unexpectedly
4. **Check Logs**: Review gateway logs for detailed errors
5. **Update Tests**: Keep tests in sync with API changes

## Performance

### Test Duration

Typical execution time:
- Gateway health check: < 1 second
- Per server test suite: 5-15 seconds
- Total for 5 servers: ~45-60 seconds

### Rate Limiting

Tests respect rate limits:
- Each test uses minimal API calls
- Pauses between tests (if needed)
- Safe to run repeatedly

## Monitoring

### Test Metrics

Track these over time:
- Pass/fail rate per server
- Test duration
- Authentication failures
- API errors

### Alerting

Set up alerts for:
- All tests failing (gateway down)
- Specific server failing (credential issue)
- Increased test duration (performance degradation)

## Resources

- Full documentation: `MCP_INTEGRATIONS.md`
- Quick start guide: `MCP_QUICKSTART.md`
- OAuth setup: `setup_google_oauth.py`
- Gateway logs: `docker compose logs gateway`

## Support

If tests are failing:

1. Check gateway status: `curl http://localhost:9100/health`
2. Verify credentials in `.env.mcpjungle`
3. Review gateway logs: `docker compose logs -f gateway`
4. Test individual server with curl
5. Check external service status pages
