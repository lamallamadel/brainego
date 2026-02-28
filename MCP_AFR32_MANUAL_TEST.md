# AFR-32 Manual Test - MCP GitHub/Notion Registration + ACL

This procedure validates:
1. `mcp-github` and `mcp-notion` are registered in MCPJungle.
2. ACL role `project-agent` is available.
3. `project-agent` can discover tools and execute simple read calls.

## Preconditions

- `configs/mcp-servers.yaml` and `configs/mcp-acl.yaml` are deployed.
- `.env.mcpjungle` contains:
  - `GITHUB_TOKEN`
  - `NOTION_API_KEY`
  - `GITHUB_TEST_OWNER`, `GITHUB_TEST_REPO_1`, `GITHUB_TEST_REPO_2`
  - `NOTION_TEST_WORKSPACE_ID`, `NOTION_TEST_DATABASE_ID_1`, `NOTION_TEST_DATABASE_ID_2`
- Gateway is running on `http://localhost:9100`.

## 1) Verify role mapping (`project-agent`)

```bash
curl -s -H "Authorization: Bearer sk-project-agent-key-321" \
  http://localhost:9100/mcp/acl/role | jq
```

Expected:
- `role` is `project-agent`
- Only `mcp-github` and `mcp-notion` are listed in `servers`
- operations are read-only

## 2) Verify server discovery

```bash
curl -s -H "Authorization: Bearer sk-project-agent-key-321" \
  http://localhost:9100/mcp/servers | jq
```

Expected:
- Response includes `mcp-github` and `mcp-notion`
- No privileged/unrelated servers should be required for this role

## 3) Verify tool discovery (GitHub)

```bash
curl -s -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/list \
  -d '{"server_id":"mcp-github"}' | jq
```

Expected:
- Includes read tools such as `github_search_repositories`, `github_get_repository`
- Does not include write/admin tools

## 4) Verify simple GitHub call

```bash
curl -s -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/call \
  -d '{
    "server_id":"mcp-github",
    "tool_name":"github_get_repository",
    "arguments":{"owner":"YOUR_TEST_OWNER","repo":"YOUR_TEST_REPO"}
  }' | jq
```

Expected:
- `result.isError` is `false`
- Repository metadata is returned

## 5) Verify tool discovery (Notion)

```bash
curl -s -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/list \
  -d '{"server_id":"mcp-notion"}' | jq
```

Expected:
- Includes read tools such as `notion_search`, `notion_get_page`, `notion_query_database`
- Does not include write tools (`notion_create_page`, `notion_update_page`)

## 6) Verify simple Notion call

```bash
curl -s -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/call \
  -d '{
    "server_id":"mcp-notion",
    "tool_name":"notion_search",
    "arguments":{"query":"test","page_size":5}
  }' | jq
```

Expected:
- `result.isError` is `false`
- Search results from test workspace are returned

## 7) Negative check (write denied)

```bash
curl -s -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  http://localhost:9100/mcp/tools/call \
  -d '{
    "server_id":"mcp-notion",
    "tool_name":"notion_create_page",
    "arguments":{"parent":{"database_id":"db"},"properties":{}}
  }' | jq
```

Expected:
- HTTP 403 due to ACL restriction

