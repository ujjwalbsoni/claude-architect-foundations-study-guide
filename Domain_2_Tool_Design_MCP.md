# Domain 2: Tool Design & MCP Integration (18% of CCA-F)

> ~11 of 60 questions. Smaller than D1 but the **lowest pass rate** in Anthropic's
> internal beta — candidates underestimate it because "MCP looks like just an API."
> The exam tests whether you make the right *boundary decisions*: where a tool
> stops, where another tool begins, where MCP fits versus a direct SDK tool.

---

## 2.0 Mental Model — Tools, MCP, and Why They Aren't the Same Thing

Two layers, often conflated:

| Layer                       | What it is                                                                                 |
|-----------------------------|--------------------------------------------------------------------------------------------|
| **Anthropic tool use**      | The wire-level protocol Claude uses to request a function call (`tool_use` blocks in the API)|
| **Model Context Protocol (MCP)** | A standard for exposing tools, prompts, and resources from an external server to *any* MCP-aware client (Claude Code, Claude Desktop, your app) |

The *exam-critical* insight: **MCP is a packaging and distribution standard for
tools**, not a different API. A Claude API call still receives `tool_use` blocks;
MCP is how the host application *discovers* and *invokes* tools without bespoke
integration code.

```
┌──────────────────────────────────────────────────────────────┐
│  Your application / Claude Code  (MCP CLIENT)                │
│                                                              │
│      ▲   tool schemas advertised at startup                  │
│      │   tool calls dispatched at runtime                    │
│      ▼                                                       │
│   ┌──────────────┐    ┌──────────────┐   ┌──────────────┐    │
│   │ MCP server A │    │ MCP server B │   │ MCP server C │    │
│   │ (filesystem) │    │ (postgres)   │   │ (custom-biz) │    │
│   └──────────────┘    └──────────────┘   └──────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### Three primitives an MCP server can expose

| Primitive  | Purpose                                                | Claude consumes as…                       |
|------------|--------------------------------------------------------|-------------------------------------------|
| **Tools**  | Side-effecting functions (read/write/act)              | `tool_use` blocks                          |
| **Resources** | Read-only addressable content (`file://`, `db://`)  | Attached to context (like RAG snippets)   |
| **Prompts** | Server-defined templated prompts the user can invoke  | Inserted as user/system messages          |

If a question asks "best way to expose a read-only Postgres view to Claude" — the
answer is a **resource**, not a tool. Resources don't burn tool-call turns and
don't need a schema for inputs.

---

## 2.1 Tool Schema Design — The Five Rules

The exam loves schema-quality questions. Memorize these rules; they're how
distractors are constructed.

### Rule 1 — The name is part of the prompt

Tool names are tokens Claude sees. `search_users` and `query_users_v2` are not
interchangeable to the model. Use **verb_noun**, snake_case, ≤30 chars.

```python
# BAD — meaningless number, no verb, ambiguous "object"
{"name": "users_3", "description": "user thing"}

# GOOD — verb_noun, scoped, self-describing
{"name": "search_users_by_email", "description": "..."}
```

### Rule 2 — The description IS the documentation Claude reads

Claude has never seen your code. The description is the *only* signal it has for
when to use the tool versus another. Treat it like a docstring written for a
junior engineer.

```python
{
    "name": "search_users_by_email",
    "description": (
        "Find a user by exact email address (case-insensitive). "
        "Returns one record or null. "
        "Use this for login lookups and account recovery. "
        "Do NOT use this for partial / fuzzy matches — use search_users_fulltext."
    ),
    "input_schema": { ... },
}
```

The "Do NOT use this for X" sentence is the highest-ROI line you can write. It
explicitly disambiguates against neighboring tools and slashes wrong-tool errors.

### Rule 3 — Constrain inputs as tightly as possible

Use `enum`, `pattern`, `minimum`, `maximum`, `format`. Each constraint is a
guard the model receives for free.

```python
"input_schema": {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "pattern": "^usr_[A-Za-z0-9]{12}$"},
        "currency": {"type": "string", "enum": ["USD", "EUR", "GBP"]},
        "amount_cents": {"type": "integer", "minimum": 1, "maximum": 100_00000},
    },
    "required": ["user_id", "currency", "amount_cents"],
    "additionalProperties": False,    # reject extras — catches hallucinations
}
```

`additionalProperties: false` is the silent-MVP. It turns a fuzzy schema into a
contract.

### Rule 4 — Outputs are also a schema (even if the API doesn't enforce one)

Claude's API does not have a formal output schema, but **what your tool returns
becomes the next assistant turn's input**. Garbage out → garbage in next turn.

- Always return JSON (a string of JSON, since `tool_result.content` is text or blocks).
- Include the same shape on success and failure (e.g. always have a `status` field).
- Cap result size — a 50KB tool output will dominate the context window.

```python
def get_order(order_id: str) -> str:
    try:
        order = db.fetch(order_id)
        return json.dumps({"status": "ok", "order": order})
    except NotFound:
        return json.dumps({"status": "not_found", "order_id": order_id})
    except Exception as e:
        # Return as data, not raise — the model can recover
        return json.dumps({"status": "error", "message": str(e)})
```

### Rule 5 — Boundary discipline (the most-failed exam topic)

> **A tool should do one thing whose contract you'd put on a whiteboard.**

If your tool description contains "and" or "either", you probably want **two
tools**. Common antipatterns that get punished on the exam:

| Antipattern                                     | Why wrong                                         | Fix                                       |
|-------------------------------------------------|---------------------------------------------------|-------------------------------------------|
| `manage_user(action: create|update|delete)`     | The model has to encode policy in `action`        | Three tools: `create_user`, `update_user`, `delete_user` |
| `query_db(sql: string)`                         | Hands the model arbitrary SQL — security + boundary disaster | Domain-specific tools per query shape |
| `do_anything(intent: string)`                   | Boundary doesn't exist                            | Decompose into named tools                |
| `search(thing: string, kind: string)`           | Two boundaries pretending to be one               | `search_users`, `search_orders`, ...     |
| Tool that returns **and** writes                | Side-effect ambiguity for the planner             | Split read/write                          |

**Exam framing:** "An agent occasionally invokes the wrong tool variant" → the fix
is almost always **tighter boundaries** (split the tool / improve description),
not "use a smarter model".

---

## 2.2 Anthropic SDK — Direct Tools (No MCP)

The simplest tool-use model: tools live in your client process and you handle the
loop. Use this when:

- You only have one host application.
- You don't need cross-app reuse.
- Latency matters and you don't want a separate process.

```python
"""
direct_tools.py — tools defined inline in the client process.

This is the default unless you have a reason to reach for MCP. MCP adds value when
you want REUSE across hosts, AUTH boundaries between tool and model, or distribution
of tools as servers others can install.
"""
import os, json, sqlite3
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
db = sqlite3.connect("orders.db")

TOOLS = [
    {
        "name": "get_order",
        "description": "Fetch an order by ID. Returns one record or {'status':'not_found'}.",
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "string", "pattern": "^ord_[A-Za-z0-9]{10}$"}},
            "required": ["order_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "refund_order",
        "description": (
            "Issue a refund for an order. SIDE-EFFECT: changes order state. "
            "Requires the order to be in 'paid' status. "
            "Use ONLY after confirming the order details with get_order first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "pattern": "^ord_[A-Za-z0-9]{10}$"},
                "reason_code": {"type": "string", "enum": ["customer_request", "fraud", "duplicate", "defective"]},
            },
            "required": ["order_id", "reason_code"],
            "additionalProperties": False,
        },
    },
]

def execute(name, args):
    if name == "get_order":
        row = db.execute("SELECT id, status, amount_cents FROM orders WHERE id=?",
                         (args["order_id"],)).fetchone()
        if not row:
            return json.dumps({"status": "not_found", "order_id": args["order_id"]})
        return json.dumps({"status": "ok", "id": row[0], "state": row[1], "amount_cents": row[2]})
    if name == "refund_order":
        # SPIDER Defend right at the boundary: enforce the precondition in CODE,
        # not just in the tool description. The description is advisory; this is policy.
        row = db.execute("SELECT status FROM orders WHERE id=?", (args["order_id"],)).fetchone()
        if not row:
            return json.dumps({"status": "not_found"})
        if row[0] != "paid":
            return json.dumps({"status": "error", "message": f"order is {row[0]}, not paid"})
        db.execute("UPDATE orders SET status='refunded' WHERE id=?", (args["order_id"],))
        return json.dumps({"status": "ok", "order_id": args["order_id"], "refunded": True})
    return json.dumps({"status": "error", "message": f"unknown tool {name}"})

def chat(user_msg):
    messages = [{"role": "user", "content": user_msg}]
    while True:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=2048,
            tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "end_turn":
            return "".join(b.text for b in resp.content if b.type == "text")
        if resp.stop_reason == "tool_use":
            results = []
            for blk in resp.content:
                if blk.type == "tool_use":
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": blk.id,
                        "content": execute(blk.name, blk.input),
                    })
            messages.append({"role": "user", "content": results})
            continue
        return f"[stopped: {resp.stop_reason}]"
```

### Server-side tools (built-ins) — exam knowledge

Anthropic provides server-executed tools that you don't have to implement:

| Tool                          | Type token                          | What it does                            |
|-------------------------------|-------------------------------------|-----------------------------------------|
| **Web search**                | `web_search_20250305`               | Live web search; results inserted as context |
| **Code execution**            | `code_execution_20250522`           | Sandboxed Python in Anthropic-hosted env |
| **Computer use**              | `computer_20241022`                 | Screen + mouse + keyboard control       |
| **Text editor**               | `text_editor_20250124`              | File read/edit primitives               |
| **Bash**                      | `bash_20250124`                     | Shell command execution                 |

You declare them in `tools=[{"type": "<token>", "name": "<name>", ...}]`. The SDK
auto-executes server-side ones; you only handle results.

> **Exam gotcha:** A common distractor pairs "needs live web data" with
> "build a custom MCP search server." The right answer is the **built-in
> `web_search` tool** unless the scenario *also* says "must use our internal
> search index" or "results must be replayable from a private corpus."

---

## 2.3 MCP — When and Why

MCP became valuable when these three things were true at once:

1. **Multiple hosts** want the same tools (Claude Code, Claude Desktop, your app).
2. **Tools live in their own process** — different security boundary, different
   language, different auth.
3. **Discovery should be config-driven** — operators add a server entry, the client
   advertises the tools to the model, no code change.

### MCP architecture (one-page version)

```
        ┌────────────────────┐                       ┌────────────────────┐
        │       HOST         │   JSON-RPC over       │     MCP SERVER     │
        │  (Claude Code,     │   stdio | SSE | HTTP  │  (filesystem,      │
        │   Claude Desktop,  │ ◄────────────────────►│   postgres,        │
        │   your app)        │                       │   github, custom)  │
        └────────────────────┘                       └────────────────────┘
            │                                                  ▲
            │ tools advertised at handshake                    │ runs the
            │ Claude API call w/ those tool schemas            │ actual code
            ▼                                                  │
        ┌────────────────────┐                                 │
        │   Claude API       │ ── tool_use ── host ── tool_call ┘
        └────────────────────┘
```

**Key fact:** Claude does *not* talk to the MCP server directly. The host is the
glue. Claude emits `tool_use`; the host routes it via JSON-RPC to the right MCP
server; the host returns the JSON-RPC response as `tool_result`.

---

## 2.4 Transports — `stdio` vs `SSE` vs `HTTP`

This single decision is over-represented on the exam.

| Transport     | Wire                          | Process model                   | Best for                                | Auth                              |
|---------------|-------------------------------|---------------------------------|-----------------------------------------|-----------------------------------|
| **stdio**     | stdin/stdout pipes (JSON-RPC) | Server is a child process of host | Local-only tools (filesystem, git, dev tools) | Implicit (process boundary)       |
| **SSE**       | Server-Sent Events over HTTP  | Server is a remote HTTP service | Remote tools, multi-tenant, prod        | Headers / OAuth / mTLS            |
| **HTTP (streamable)** | Streamable HTTP (newer)| Server is a remote HTTP service | Same as SSE, simpler infra              | Same                              |

### Decision rule (memorize)

```
Does the tool need to run on the user's machine (local files, dev env, OS)?
    YES → stdio.   Don't expose a network surface for no reason.
    NO  → does it need to be reachable by multiple clients / users?
        YES → SSE or HTTP.
        NO  → stdio still fine if a single host owns it.
```

### Why stdio for local tools — security argument

A `filesystem` MCP server over SSE is a **remote-code-execution risk**: anyone
who reaches the port reads/writes the user's disk. Stdio confines the tool to the
host process tree, the OS user, and the lifetime of the host. The exam will plant
"expose filesystem MCP over SSE for convenience" as a distractor — it's wrong.

### Why SSE for remote/multi-tenant — operational argument

If 50 engineers should share one Postgres MCP server, you can't give them all
50 child processes with credentials. You run one server with auth, OAuth scopes
per user, and audit logs. That requires HTTP.

### `stdio` minimal MCP server in Python

```python
"""
mcp_server_stdio.py — minimal MCP server over stdio.

Run with: claude_desktop_config.json or .mcp.json:
{
  "mcpServers": {
    "demo": { "command": "python", "args": ["mcp_server_stdio.py"] }
  }
}
"""
import asyncio
from mcp.server import Server                  # `pip install mcp`
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("demo-mcp")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="add_numbers",
            description="Add two integers and return the sum.",
            inputSchema={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "add_numbers":
        result = arguments["a"] + arguments["b"]
        return [TextContent(type="text", text=str(result))]
    raise ValueError(f"unknown tool: {name}")

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

### `SSE` minimal MCP server (FastAPI + the official `mcp` SDK)

```python
"""
mcp_server_sse.py — remote MCP server over SSE.

Run with: uvicorn mcp_server_sse:app --port 8000
Client config:
{
  "mcpServers": {
    "demo-remote": { "url": "https://mcp.example.com/sse" }
  }
}
"""
from fastapi import FastAPI, Request, Header, HTTPException
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

server = Server("demo-remote")

@server.list_tools()
async def list_tools():
    return [Tool(name="echo",
                 description="Echo the input string.",
                 inputSchema={"type": "object",
                              "properties": {"msg": {"type": "string"}},
                              "required": ["msg"]})]

@server.call_tool()
async def call_tool(name, args):
    return [TextContent(type="text", text=args["msg"])]

app = FastAPI()
sse = SseServerTransport("/messages/")

@app.get("/sse")
async def handle_sse(req: Request, authorization: str = Header(None)):
    # AUTH at the transport boundary — exam-favored pattern
    if not _verify_token(authorization):
        raise HTTPException(401, "invalid token")
    async with sse.connect_sse(req.scope, req.receive, req._send) as (r, w):
        await server.run(r, w, server.create_initialization_options())

app.mount("/messages/", sse.handle_post_message)

def _verify_token(header):
    return header and header.startswith("Bearer ") and _check(header.split()[1])
```

Note where auth is enforced: at the **HTTP boundary**, before the MCP session
even starts. Inside an MCP session, you can't add per-call auth; you check
identity at handshake.

---

## 2.5 Auth Patterns

Three patterns, each with a use case the exam rewards:

### 2.5.1 Static API token (header)

```
Authorization: Bearer <token>
```

- Simplest. Use for service-to-service or single-user dev.
- One token = one identity; rotation is painful at scale.
- **Don't** put the token in the tool input schema. Tokens never go through the
  model.

### 2.5.2 OAuth 2.0 / per-user delegation

- The MCP server presents an OAuth flow; the host opens a browser; the user
  consents; the server stores a per-user refresh token.
- Mandatory whenever the tool acts **on behalf of** the user (e.g. send their
  email, post their tweets).
- Exam-favored answer for "GitHub MCP server in a multi-user IDE plugin."

### 2.5.3 mTLS / network-level

- Both sides present certs.
- Use inside controlled VPCs / SREs only.
- Almost never the right exam answer for a *user-facing* server.

### Anti-pattern

> **Putting credentials in tool inputs.** The model should never see secrets,
> even encrypted. Secrets live in the host's MCP server config or the server's
> own secret store. Distractors will phrase this as "pass the API key as a tool
> argument so the agent can choose which account to use" — wrong every time.

---

## 2.6 Resources — The Forgotten Primitive

Every CCA-F form has 1–2 questions that test whether you reach for **resources**
instead of tools.

| Question form                                 | Right primitive |
|-----------------------------------------------|-----------------|
| "Expose a read-only data set"                 | Resource        |
| "Let Claude pick from a catalog of files"     | Resource        |
| "Run a query the user wrote"                  | Tool            |
| "Trigger a side effect"                       | Tool            |
| "Reusable templated prompt"                   | Prompt          |

### Resource example

```python
@server.list_resources()
async def list_resources():
    return [
        Resource(uri="docs://api/users",
                 name="Users API spec",
                 mimeType="text/markdown"),
        Resource(uri="db://orders/schema",
                 name="Orders DB schema",
                 mimeType="application/json"),
    ]

@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "docs://api/users":
        return open("docs/users.md").read()
    if uri == "db://orders/schema":
        return json.dumps(get_orders_schema())
    raise ValueError(f"unknown resource: {uri}")
```

The host attaches the resource content to the model's context as a *file* or
inline block, **without burning a tool-call turn**. That's the architectural win:
context delivery without round-trips.

---

## 2.7 Resource Management — Limits, Quotas, Lifecycle

Production MCP servers fail in three predictable ways. The exam tests whether
you've thought about each.

### 2.7.1 Connection lifecycle

- One MCP session per host process. Don't reconnect per tool call.
- On host shutdown, send a clean `shutdown` so the server can release locks /
  flush logs. Stdio servers should handle SIGTERM gracefully.

### 2.7.2 Tool execution limits

- Set a per-tool timeout (default ~30s in Claude Code; configurable).
- Cap concurrent tool executions per session — runaway loops can spawn 100+
  parallel tool calls.
- Prefer **idempotent** tools wherever possible (retry-safe).

### 2.7.3 Result size

- Keep tool results <8 KB if you can; **cap at 50 KB**. A 1 MB tool result will
  silently consume your entire context window.
- Pagination is the right answer for "list all rows" tools — return `next_cursor`,
  not the whole table.

### 2.7.4 The "thundering herd" problem

If your MCP server is shared across 50 Claude Code users and a popular tool slows
down, every host stalls. Mitigations:

- Per-user concurrency caps in the server.
- Circuit breakers (return `status: degraded` instead of timing out).
- Async tools with a `pending` poll pattern for jobs >5s.

---

## 2.8 MCP Client Configuration

You'll see config snippets on the exam. Learn the two formats.

### Claude Desktop / Claude Code config (`.mcp.json` or settings)

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${env:GH_TOKEN}" }
    },
    "postgres": {
      "command": "uvx",
      "args": ["mcp-server-postgres", "postgresql://app:***@db/prod"]
    },
    "remote-search": {
      "url": "https://search-mcp.internal.corp/sse",
      "headers": { "Authorization": "Bearer ${env:SEARCH_TOKEN}" }
    }
  }
}
```

### Claude Code scope hierarchy (CRITICAL — also asked in D3)

| Scope        | Path                                | Who sees it                       |
|--------------|-------------------------------------|-----------------------------------|
| **Project**  | `<repo>/.mcp.json`                  | Anyone running Claude Code in repo |
| **User**     | `~/.claude.json` (mcpServers section) | All your projects                |
| **Local**    | `<repo>/.claude/settings.local.json` | Only you, only this repo          |

**Exam gotcha:** "How do you give every engineer the same MCP server without
checking secrets into git?" → put the **server entry** in `.mcp.json` (committed)
and the **secret** in `.env` referenced via `${env:...}` (gitignored). Don't
inline tokens.

---

## 2.9 Tool Boundary Decisions — the Exam's Favorite Trap

A 4-cell mental matrix:

```
                    │  Same context window OK?
                    │   YES         │   NO
   ─────────────────┼───────────────┼──────────────────
   Deterministic?   │ direct tool   │ subagent over the tool
   YES              │ (most common) │ (rare; e.g. tool returns 100KB)
   ─────────────────┼───────────────┼──────────────────
   Needs reasoning? │ subagent      │ subagent
   NO (plain call)  │ (Domain 1)    │ (Domain 1)
```

**Pop-quiz:** "Should the email-drafting capability be a tool or a subagent?"
Drafting requires reasoning across context → **subagent**. Sending the email is
deterministic → **tool**. Two primitives, not one.

### Common boundary mistakes the exam punishes

| Mistake                                                    | What to pick instead                            |
|------------------------------------------------------------|-------------------------------------------------|
| One mega-tool with `action` enum dispatching internally    | One tool per action                             |
| Tool that returns AND writes (e.g. `get_or_create_user`)   | Two tools: `get_user`, `create_user`            |
| Free-form `query(sql)` tool                                | Domain-specific query tools (`search_users_by_email`, …) |
| MCP server exposing 80 tools                               | Group by capability into 2–4 servers; cap each at ~12 tools (the model degrades past ~40) |
| Mixing read-only catalog data into tool calls              | Expose as **resources**                         |

---

## 2.10 End-to-End Example — Custom MCP Server with Auth, Resources, and Tools

This is the kind of system the exam scenarios reference.

```python
"""
billing_mcp.py — production-shaped MCP server for billing operations.

Demonstrates ALL the patterns the exam expects:
  * Tools with tight boundaries (one verb each)
  * A resource (read-only invoice catalog)
  * Bearer-token auth at the SSE transport boundary
  * Result size capping + pagination
  * Idempotency (refund_invoice keyed on idempotency_key)
"""
from fastapi import FastAPI, Request, Header, HTTPException
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, Resource, TextContent
import os, json, hmac

server = Server("billing-mcp")
INVOICES = {}      # mock store
REFUND_KEYS = {}   # idempotency

# ---------- Resources -----------------------------------------------------
@server.list_resources()
async def list_resources():
    return [Resource(
        uri="billing://invoices/index",
        name="Invoice catalog (read-only)",
        mimeType="application/json",
    )]

@server.read_resource()
async def read_resource(uri: str) -> str:
    if uri == "billing://invoices/index":
        # Return a SUMMARY, not the full data; agents follow up with get_invoice
        return json.dumps([{"id": k, "total_cents": v["total_cents"], "status": v["status"]}
                           for k, v in INVOICES.items()])
    raise ValueError(uri)

# ---------- Tools ---------------------------------------------------------
@server.list_tools()
async def list_tools():
    return [
        Tool(name="get_invoice",
             description="Fetch a single invoice by ID. Read-only.",
             inputSchema={"type": "object",
                          "properties": {"invoice_id": {"type": "string", "pattern": "^inv_[a-z0-9]{10}$"}},
                          "required": ["invoice_id"], "additionalProperties": False}),
        Tool(name="refund_invoice",
             description=("Issue a full refund. SIDE-EFFECT. "
                          "Requires the invoice to be in 'paid' state. "
                          "Pass a unique idempotency_key — repeated calls with the same key return the same result."),
             inputSchema={"type": "object",
                          "properties": {
                              "invoice_id": {"type": "string", "pattern": "^inv_[a-z0-9]{10}$"},
                              "idempotency_key": {"type": "string", "minLength": 8, "maxLength": 64},
                              "reason": {"type": "string", "enum": ["fraud", "customer_request", "duplicate"]},
                          },
                          "required": ["invoice_id", "idempotency_key", "reason"],
                          "additionalProperties": False}),
    ]

@server.call_tool()
async def call_tool(name, args):
    if name == "get_invoice":
        inv = INVOICES.get(args["invoice_id"])
        if not inv:
            return [TextContent(type="text", text=json.dumps({"status": "not_found"}))]
        return [TextContent(type="text", text=json.dumps({"status": "ok", "invoice": inv}))]
    if name == "refund_invoice":
        # Idempotency before any state change — exam-favored pattern
        if args["idempotency_key"] in REFUND_KEYS:
            return [TextContent(type="text", text=json.dumps(REFUND_KEYS[args["idempotency_key"]]))]
        inv = INVOICES.get(args["invoice_id"])
        if not inv or inv["status"] != "paid":
            res = {"status": "error", "message": "invoice not in paid state"}
        else:
            inv["status"] = "refunded"
            res = {"status": "ok", "invoice_id": args["invoice_id"], "refunded": True}
        REFUND_KEYS[args["idempotency_key"]] = res
        return [TextContent(type="text", text=json.dumps(res))]
    raise ValueError(name)

# ---------- Transport + Auth ---------------------------------------------
app = FastAPI()
sse = SseServerTransport("/messages/")

def _verify(token: str) -> bool:
    expected = os.environ["BILLING_MCP_TOKEN"].encode()
    return hmac.compare_digest(token.encode(), expected)

@app.get("/sse")
async def sse_endpoint(req: Request, authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401)
    if not _verify(authorization.removeprefix("Bearer ")):
        raise HTTPException(403)
    async with sse.connect_sse(req.scope, req.receive, req._send) as (r, w):
        await server.run(r, w, server.create_initialization_options())

app.mount("/messages/", sse.handle_post_message)
```

**What to study from this example:**
- Auth at the transport, not in tool inputs.
- Tool boundaries: `get_invoice` and `refund_invoice` are separate.
- Idempotency built into the destructive tool's schema.
- Resource for the catalog (read-only browsing) so agents don't burn turns listing.
- Result size: never returns the whole INVOICES table, only one record or a slim index.

---

## 2.11 Practice MCQs (Domain 2)

---

**Q1.** Your team is building a Claude Desktop plugin that needs to read and
edit local files in the user's home directory. The plugin is for individual
developers, not multi-tenant. Which MCP transport is correct?

A. SSE over HTTPS, with an OAuth flow against your company SSO.
B. stdio, with the MCP server launched as a child process of Claude Desktop.
C. mTLS over HTTP, with both sides presenting certs.
D. WebSocket to a self-hosted relay.

---

**Q2.** A team builds an MCP server with a single tool:

```
manage_user(action: "create" | "update" | "delete", payload: object)
```

In production they observe Claude **frequently picks the wrong action**. The
team's lead suggests "switching to Opus 4.7 to fix it." What's the better fix?

A. Increase `max_tokens` so Claude has room to reason about which action to take.
B. Decompose into three tools — `create_user`, `update_user`, `delete_user` —
   each with a tight description.
C. Add a system prompt sentence: "Be careful which action you pick."
D. Set `temperature=0` to eliminate variability.

---

**Q3.** You have a 50-document policy library. Engineers want Claude Code to
**reference** these docs when answering compliance questions. The docs are
read-only and stable. Which MCP primitive fits best?

A. Tools — one per document.
B. Resources — list each doc; expose `read_resource` for content.
C. A single `query_policies(query: string)` tool that searches them.
D. Hard-code the docs in CLAUDE.md.

---

**Q4.** A teammate proposes adding `db_token` and `db_user` as required fields
in every database tool's input schema, "so the model can pick the right account
per query." What's wrong?

A. Nothing — this is the recommended pattern.
B. Credentials must never appear in tool inputs; the model would see them.
   Auth belongs at the host/transport boundary, not in the schema.
C. Tool inputs must be primitive types only — no strings allowed.
D. Database tools must always be read-only; mutation needs an SDK call.

---

**Q5.** Your MCP server is shared by 40 Claude Code users. One slow tool starts
timing out, and **every user's session stalls**. Which is the strongest fix?

A. Add per-user concurrency caps + circuit breaker that returns `status: degraded`
   instead of timing out.
B. Switch the transport to stdio so each user has their own process.
C. Increase the host-side tool timeout from 30s to 5 minutes.
D. Move the slow tool to a subagent.

---

**Q6.** You need to expose a `web_search` capability so Claude can ground
answers in current events. There is no compliance requirement to use a private
search index. Which is best?

A. Build a custom MCP server wrapping Bing's API.
B. Use Anthropic's built-in **web search** server-side tool
   (`web_search_20250305`).
C. Add a `web_search` tool that wraps Google scraping.
D. Use computer-use to drive a browser.

---

**Q7.** A user-facing IDE plugin must let Claude open issues in the user's
GitHub on the user's behalf. Which auth pattern is correct?

A. A static API token shared by all users, stored in the MCP server's env.
B. OAuth 2.0 per user, with refresh tokens stored by the MCP server, scoped to
   the actions the user consented to.
C. Pass the user's PAT as a tool input on each call.
D. mTLS between the IDE and the MCP server.

---

**Q8.** Your MCP server's `list_orders` tool currently returns the full order
table (~2 MB of JSON). After integration, **agent quality drops sharply** mid-
conversation. The most direct fix is:

A. Switch the model to a 1M-context variant.
B. Add pagination: return a page plus `next_cursor`, capped at <8 KB per call.
C. Remove the tool description so Claude calls it less often.
D. Move the tool to a separate MCP server.

---

**Q9.** You want every engineer in the repo to share a Postgres MCP server
config, but the connection string contains a password. Where does each piece go?

A. Both the `mcpServers.postgres` entry and the password in `.mcp.json`,
   committed to git.
B. The `mcpServers.postgres` entry in committed `.mcp.json`, the password
   referenced via `${env:PG_PASSWORD}` and provided through `.env` (gitignored).
C. Both entirely in `~/.claude.json` per engineer.
D. In `settings.local.json` so it's never committed.

---

**Q10.** A team's MCP server currently advertises **63 tools**. The agent's
tool-selection accuracy is low. What is the most defensible refactor?

A. Reduce to ~12 well-bounded tools; group remaining capabilities into a
   second MCP server, or expose them as resources/prompts.
B. Keep all 63 tools but add long descriptions to each.
C. Split into 63 separate MCP servers, one per tool.
D. Replace tools with a single "do_anything" entry point.

---

### Answers & Rationale

| Q  | Ans | Why                                                                                        |
|----|-----|--------------------------------------------------------------------------------------------|
| 1  | B   | Local file access ⇒ stdio. SSE for files is a remote-RCE risk. **2.4**                      |
| 2  | B   | Boundary decomposition is the right fix; model swap doesn't address the design defect.    |
| 3  | B   | Read-only addressable content = **resource**, not tool.                                    |
| 4  | B   | Secrets never go through the model; auth lives at the transport boundary.                  |
| 5  | A   | Multi-tenant degradation needs server-side concurrency caps + circuit breakers.            |
| 6  | B   | Built-in `web_search` is the right answer unless a private index is required.              |
| 7  | B   | Acting on behalf of a user requires OAuth + per-user refresh tokens + scopes.              |
| 8  | B   | Result-size cap with pagination — direct fix to context-window saturation.                 |
| 9  | B   | Committed config + env-referenced secret is the canonical pattern.                         |
| 10 | A   | Tool-list size degrades selection past ~40; group/refactor, don't pile on descriptions.    |

---

## 2.12 Mini-Lab — Build an Auditable "Notes" MCP Server

**Goal:** A Python MCP server that exposes a per-user notes API:

- Tools: `create_note`, `update_note`, `delete_note`, `search_notes`.
- Resource: `notes://index` — lists titles only (read-only catalog).
- Auth: Bearer token via SSE.
- Idempotency on `create_note` and `update_note`.
- Result-size cap on `search_notes` (paginated).
- Audit log: every mutating call writes a JSON line to `audit.log`.

**Acceptance criteria:**
1. `claude` CLI configured with the server can list its tools and resources.
2. Re-running `create_note` with the same `idempotency_key` returns the same id.
3. `search_notes` with no cursor returns ≤ 25 results + `next_cursor`.
4. Unauthenticated SSE connections return 401.
5. The audit log contains one line per mutating call with timestamp, tool, args
   (minus secrets), and result status.

**Stretch goals:**
- Add a critic tool `validate_note(text)` that flags PII and refuses to store it.
- Add per-user concurrency caps (max 3 in-flight tool calls per token).
- Switch the transport to streamable HTTP and add a feature-detection probe.

---

## 2.13 Domain 2 Cheatsheet (flashcard-ready)

```
══════════════════════════════════════════════════════════════════════════
DOMAIN 2 — TOOL DESIGN & MCP INTEGRATION   (18%)
══════════════════════════════════════════════════════════════════════════

THREE PRIMITIVES (MCP)
  Tools     → side-effecting functions       → tool_use blocks
  Resources → read-only addressable content  → attached to context
  Prompts   → templated user/system prompts  → chosen by user

TRANSPORT DECISION
  Local-only / per-user           → stdio
  Multi-user / remote / prod      → SSE or streamable HTTP
  NEVER expose filesystem/dev tools over SSE without auth

TOOL SCHEMA — FIVE RULES
  1. Name = part of the prompt; verb_noun, snake_case, ≤30 chars
  2. Description = the docstring Claude reads; include "Do NOT use for X"
  3. Tighten inputs: enum, pattern, min/max, additionalProperties:false
  4. Outputs are a de-facto schema; always JSON, status on every path
  5. Boundary: one verb per tool — split anything with "and" / "or"

OUTPUT GUARDRAILS
  - Cap results at 8 KB; absolute max 50 KB
  - Paginate "list" tools; return next_cursor
  - Return errors as data (status:"error"); NEVER raise

SERVER-SIDE BUILT-INS (don't reinvent)
  web_search_20250305    — live web search
  code_execution_20250522— sandboxed Python
  computer_20241022      — screen + I/O
  text_editor / bash     — file & shell

AUTH PATTERNS
  Static bearer  → service-to-service / single-user dev
  OAuth per user → user-acting tools (mandatory for "on behalf of")
  mTLS           → controlled VPC SRE only
  ANTI-PATTERN  → credentials in tool inputs (model must never see secrets)

TOOL vs SUBAGENT vs RESOURCE
  Deterministic capability, fits in context  → TOOL
  Reasoning + multi-turn capability          → SUBAGENT (D1)
  Read-only addressable content              → RESOURCE
  Tool returns >8KB regularly                → consider summarizing or splitting

CONFIG SCOPES (CC / CD)
  .mcp.json (project, committed)        → shared across team
  ~/.claude.json (user)                 → all your projects
  .claude/settings.local.json (local)   → only you, only this repo
  Secrets via ${env:VAR}; never inline

OPERATIONAL CONCERNS
  Lifecycle: one session per host; clean shutdown on SIGTERM
  Concurrency: per-user caps; circuit-break instead of stalling
  Idempotency: required for destructive ops; key on idempotency_key
  Result size: paginate; never dump entire tables

EXAM ANTI-PATTERNS (instant-wrong)
  ✗ Filesystem MCP over SSE without auth
  ✗ Credentials as tool inputs
  ✗ One mega-tool with action enum
  ✗ Free-form SQL/query tool
  ✗ 60+ tools on one server
  ✗ Custom MCP wrapping built-in capabilities (web_search, code exec)
  ✗ Inlining secrets in committed .mcp.json
  ✗ Reconnecting MCP per tool call
  ✗ Returning whole tables as tool output
  ✗ Solving wrong-tool errors with a bigger model

QUICK-CHOOSER
  local files / git / dev tools    → stdio MCP (or direct tool)
  remote multi-user data           → SSE/HTTP MCP w/ auth
  read-only catalog                → resource
  user's-account actions           → OAuth MCP
  live web facts                   → built-in web_search
  internal search index            → custom MCP wrapping it
══════════════════════════════════════════════════════════════════════════
```

---

> Next: **Domain 3 — Claude Code Config & Workflows (20%)**. CLAUDE.md hierarchy is
> a high-frequency exam topic; bring your settings.json appetite.
