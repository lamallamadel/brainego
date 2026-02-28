# AFR-32 Manual Test - MCP GitHub and Notion Scoped Registration

This checklist validates:
1. MCP GitHub and Notion servers are registered.
2. `project-agent` ACL is applied.
3. Tool discovery works for both servers.
4. Simple read calls succeed.
5. Write attempts are denied for `project-agent`.

## Prerequisites

- `.env.mcpjungle` configured with:
  - `GITHUB_TOKEN`
  - `NOTION_API_KEY`
  - `GITHUB_TEST_OWNER`
  - `GITHUB_TEST_REPO_1`
  - `GITHUB_TEST_REPO_2`
  - `NOTION_TEST_WORKSPACE_ID`
  - `NOTION_TEST_DATABASE_ID_1`
  - `NOTION_TEST_DATABASE_ID_2`
- Gateway running at `http://localhost:9100`
- API key `sk-project-agent-key-321` mapped to role `project-agent`

## 1) Check role mapping

```bash
curl -sS -H "Authorization: Bearer sk-project-agent-key-321" \
  http://localhost:9100/mcp/acl/role | jq
```

Expected:
- role = `project-agent`

## 2) Check server discovery

```bash
curl -sS -H "Authorization: Bearer sk-project-agent-key-321" \
  http://localhost:9100/mcp/servers | jq
```

Expected:
- `mcp-github` listed
- `mcp-notion` listed

## 3) Tool discovery (GitHub)

```bash
curl -sS -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  -d '{"server_id":"mcp-github"}' \
  http://localhost:9100/mcp/tools/list | jq
```

Expected includes read tools such as:
- `github_get_repository`
- `github_list_issues`
- `github_get_file_contents`

## 4) Tool discovery (Notion)

```bash
curl -sS -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  -d '{"server_id":"mcp-notion"}' \
  http://localhost:9100/mcp/tools/list | jq
```

Expected includes read tools such as:
- `notion_search`
- `notion_get_page`
- `notion_query_database`

## 5) Simple GitHub read call

```bash
curl -sS -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-github",
    "tool_name": "github_get_repository",
    "arguments": {
      "owner": "'$GITHUB_TEST_OWNER'",
      "repo": "'$GITHUB_TEST_REPO_1'"
    }
  }' \
  http://localhost:9100/mcp/tools/call | jq
```

Expected:
- successful response for the allowed test repo

## 6) Simple Notion read call

```bash
curl -sS -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-notion",
    "tool_name": "notion_query_database",
    "arguments": {
      "database_id": "'$NOTION_TEST_DATABASE_ID_1'",
      "page_size": 1
    }
  }' \
  http://localhost:9100/mcp/tools/call | jq
```

Expected:
- successful response scoped to the allowed test database

## 7) Negative ACL test (write denied)

GitHub write attempt:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-github",
    "tool_name": "github_create_issue",
    "arguments": {
      "owner": "'$GITHUB_TEST_OWNER'",
      "repo": "'$GITHUB_TEST_REPO_1'",
      "title": "ACL test - should fail"
    }
  }' \
  http://localhost:9100/mcp/tools/call | jq
```

Expected:
- authorization error / denied operation

Notion write attempt:

```bash
curl -sS -X POST \
  -H "Authorization: Bearer sk-project-agent-key-321" \
  -H "Content-Type: application/json" \
  -d '{
    "server_id": "mcp-notion",
    "tool_name": "notion_create_page",
    "arguments": {
      "parent": {"database_id": "'$NOTION_TEST_DATABASE_ID_1'"},
      "properties": {}
    }
  }' \
  http://localhost:9100/mcp/tools/call | jq
```

Expected:
- authorization error / denied operation
