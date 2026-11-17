# Sentence Vault: a hand-written MCP server

A minimal [Model Context Protocol](https://modelcontextprotocol.io) server that lets a voice assistant save the learner's best sentences to Postgres. It runs as a **Supabase Edge Function** (Deno, TypeScript) and does not use an MCP SDK.

**Status:** working, but superseded. The voice assistant's plugin platform kept changing, and in the end a plain Google Sheet was enough: Voice SRS now captures sentences as `BEST:` lines in the email log, and the scheduler collects them in the `Sentences` tab. The server stays here as a reference implementation of a minimal MCP server.

## What it implements

| JSON-RPC method | Response |
|---|---|
| `initialize` | protocol version, `tools` capability, server info |
| `tools/list` | one tool: `save_sentence` |
| `tools/call` | inserts the row and returns a text confirmation, or `isError` |
| notification (no `id`) | `202 Accepted`, no body |
| anything else | `-32601 Method not found` |

`save_sentence` takes `sentence` (required), `keyword`, `category`, `tags[]` and `source`.

**Input handling:**
- Sentences are limited to 1,000 characters, and the short fields to 80.
- At most 10 tags are kept.
- `category` must be one of the listed values, or it is stored as null.
- Database errors are logged on the server and never returned to the caller.

**Auth:** a shared bearer key (`SENTENCE_VAULT_API_KEY`) is checked inside the function. The check compares SHA-256 digests in constant time. The function is deployed with `--no-verify-jwt`, so callers don't need a Supabase JWT. The function writes with the service-role key, and Row Level Security is on with no policies, so the public key can neither read nor write the table.

## Files

```
sentence-vault/
├── supabase/
│   ├── functions/mcp-sentence-vault/index.ts   ← the server (~200 lines)
│   └── migrations/001_sentence_vault.sql       ← table + indexes + RLS
├── mcp.example.json                            ← client config template
└── .env.example
```

## Deploy

```bash
# 1. Link your project
supabase link --project-ref <YOUR_PROJECT_REF>

# 2. Create the table
supabase db push          # or paste the migration into the SQL editor

# 3. Set the API key the clients will send
supabase secrets set SENTENCE_VAULT_API_KEY=<a-long-random-string>
#    SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are injected automatically.

# 4. Deploy without JWT verification (the function checks its own key)
supabase functions deploy mcp-sentence-vault --no-verify-jwt
```

## Try it

```bash
curl -s https://<YOUR_PROJECT_REF>.supabase.co/functions/v1/mcp-sentence-vault \
  -H "Authorization: Bearer $SENTENCE_VAULT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"save_sentence",
                 "arguments":{"sentence":"The lambent light softened the room.","keyword":"lambent"}}}'
```

## Connect a client

Copy `mcp.example.json`, fill in your project ref and key, and add it to any MCP client that supports remote Streamable-HTTP servers. **Never commit the filled-in copy.**

Lesson learned: one assistant's plugin packager only accepted a file named exactly `mcp.json`. It silently ignored `.mcp.json` and then reported that the plugin had no MCP server.
