// Sentence Vault — MCP server
//
// Minimal, hand-rolled MCP (Model Context Protocol) server over Streamable
// HTTP, exposing a single save_sentence tool. Built as an MCP server rather
// than a ChatGPT Custom GPT Action because Custom GPTs (and their OpenAPI
// Actions) retire Dec 11, 2026, while MCP connectors (ChatGPT Developer
// Mode, and later Gemini) are the durable path. No external MCP SDK is
// used since a single tool doesn't warrant the dependency; this implements
// just enough of the spec (initialize, tools/list, tools/call) for a
// non-streaming remote connector.
//
// Deployed with --no-verify-jwt: callers authenticate with
// SENTENCE_VAULT_API_KEY via a Bearer header, not a Supabase JWT.

import { createClient } from "jsr:@supabase/supabase-js@2";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL")!,
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
);

const SERVER_INFO = { name: "sentence-vault", version: "1.0.0" };
const PROTOCOL_VERSION = "2025-06-18";

const SAVE_SENTENCE_TOOL = {
  name: "save_sentence",
  description:
    "Save a voice-captured 'best-of' sentence to the learner's permanent sentence vault.",
  inputSchema: {
    type: "object",
    properties: {
      sentence: {
        type: "string",
        description:
          "The exact sentence to save, verbatim, with no paraphrasing or correction.",
      },
      keyword: {
        type: "string",
        description:
          "The focal vocabulary word the sentence was built around, if any, e.g. 'tawny'.",
      },
      category: {
        type: "string",
        enum: ["poetic", "witty", "aphorism", "business", "conversational", "imagery"],
        description: "The kind of sentence. Anything outside the list is stored as null.",
      },
      tags: {
        type: "array",
        items: { type: "string" },
        description: "Optional free-form tags.",
      },
      source: {
        type: "string",
        description: "Which assistant captured this sentence, e.g. 'claude', 'chatgpt' or 'gemini'.",
      },
    },
    required: ["sentence"],
  },
};

function jsonRpcResult(id: unknown, result: unknown): Response {
  return new Response(JSON.stringify({ jsonrpc: "2.0", id, result }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function jsonRpcError(id: unknown, code: number, message: string): Response {
  return new Response(
    JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

const CATEGORIES = new Set(SAVE_SENTENCE_TOOL.inputSchema.properties.category.enum);
const MAX_SENTENCE = 1000;
const MAX_SHORT = 80;
const MAX_TAGS = 10;

function shortString(value: unknown): string | null {
  return typeof value === "string" && value.trim()
    ? value.trim().slice(0, MAX_SHORT)
    : null;
}

function toolError(text: string) {
  return { isError: true, content: [{ type: "text", text }] };
}

async function callSaveSentence(args: Record<string, unknown>) {
  const { sentence, keyword, category, tags, source } = args ?? {};

  if (typeof sentence !== "string" || !sentence.trim()) {
    return toolError("sentence is required");
  }
  if (sentence.length > MAX_SENTENCE) {
    return toolError(`sentence is longer than ${MAX_SENTENCE} characters`);
  }

  const cleanTags = Array.isArray(tags)
    ? tags.map(shortString).filter((t): t is string => t !== null).slice(0, MAX_TAGS)
    : [];

  const { data, error } = await supabase
    .from("sentence_vault")
    .insert({
      sentence: sentence.trim(),
      keyword: shortString(keyword),
      category: typeof category === "string" && CATEGORIES.has(category) ? category : null,
      tags: cleanTags.length ? cleanTags : null,
      source: shortString(source),
    })
    .select()
    .single();

  if (error) {
    // Log the details server-side; don't hand database errors to the caller.
    console.error("save_sentence insert failed:", error.message);
    return toolError("Could not save the sentence. Try again later.");
  }

  return {
    content: [{ type: "text", text: `Saved (id ${data.id}): "${data.sentence}"` }],
  };
}

// Compare the SHA-256 digests in constant time, so response timing reveals
// nothing about how much of the key a caller got right.
async function keyMatches(given: string, expected: string): Promise<boolean> {
  const enc = new TextEncoder();
  const [a, b] = await Promise.all([
    crypto.subtle.digest("SHA-256", enc.encode(given)),
    crypto.subtle.digest("SHA-256", enc.encode(expected)),
  ]);
  const x = new Uint8Array(a);
  const y = new Uint8Array(b);
  let diff = 0;
  for (let i = 0; i < x.length; i++) diff |= x[i] ^ y[i];
  return diff === 0;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const expected = Deno.env.get("SENTENCE_VAULT_API_KEY");
  const auth = req.headers.get("Authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : "";

  if (!expected || !token || !(await keyMatches(token, expected))) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  let body: { jsonrpc?: string; id?: unknown; method?: string; params?: Record<string, unknown> };
  try {
    body = await req.json();
  } catch {
    return jsonRpcError(null, -32700, "Parse error");
  }

  const { id, method, params } = body;

  // Notifications (no id) get no response body per JSON-RPC spec.
  if (id === undefined) {
    return new Response(null, { status: 202 });
  }

  switch (method) {
    case "initialize":
      return jsonRpcResult(id, {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: {} },
        serverInfo: SERVER_INFO,
      });

    case "tools/list":
      return jsonRpcResult(id, { tools: [SAVE_SENTENCE_TOOL] });

    case "tools/call": {
      const name = params?.name;
      const args = (params?.arguments as Record<string, unknown>) ?? {};
      if (name !== "save_sentence") {
        return jsonRpcError(id, -32602, `Unknown tool: ${name}`);
      }
      const result = await callSaveSentence(args);
      return jsonRpcResult(id, result);
    }

    default:
      return jsonRpcError(id, -32601, `Method not found: ${method}`);
  }
});
