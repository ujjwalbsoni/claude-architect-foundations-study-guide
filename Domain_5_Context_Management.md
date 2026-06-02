# Domain 5: Context Management & Reliability (15% of CCA-F)

> ~9 of 60 questions. Smallest domain by weight, but it ties together every
> other domain — long-running agents, multi-turn chats, RAG-backed assistants,
> and tool-heavy systems all live or die by context-window discipline. The exam
> rewards candidates who treat the context window as a **scarce, billable
> resource** rather than a free-form scratchpad.

---

## 5.0 Mental Model — The Context Window Is a Working Set, Not a Bag

> **Every token in the context window costs money on every turn, takes
> attention away from every other token, and competes for the model's working
> memory.**

Three corollaries the exam will test:

1. **The marginal token has a cost** — both literal ($) and quality (attention
   dilution). Adding "just one more piece" of context is not free.
2. **Order, recency, and locality matter.** A relevant fact buried 50 KB into
   a 100 KB context is harder for the model to use than the same fact placed
   near the question. ("Lost-in-the-middle" effect.)
3. **Caching is an architectural primitive, not an optimization.** Production
   systems are *designed around* what's cacheable; reorder fields if you must
   to put the stable prefix first.

### Context-window sizes (memorize)

| Model              | Context window     |
|--------------------|--------------------|
| Claude Opus 4.7    | 200K tokens        |
| Claude Sonnet 4.6  | 200K tokens (1M tier available)|
| Claude Haiku 4.5   | 200K tokens        |

The exam will plant distractors saying "use a model with a larger context
window" as the fix for context bloat. **It's almost always the wrong answer.**
A bigger window doesn't fix lost-in-the-middle, doesn't reduce cost, and
doesn't fix tool-result blowup. Architectural fixes (summarization, caching,
RAG) do.

---

## 5.1 The Token Budget — How to Think About It

### What lives in the context window

```
┌────────────────────────────────────────────────────────────┐
│ system prompt          ← stable; CACHE this                │
│ tool definitions        ← stable-ish; CACHE this           │
│ persistent context      ← per-session; CACHE if reusable   │
│ conversation history    ← grows over time                  │
│ tool results            ← can be huge; CAP this            │
│ current user turn       ← always uncached                  │
│ assistant output budget ← max_tokens reserved at top       │
└────────────────────────────────────────────────────────────┘
```

The window holds **input + output**. If your `max_tokens` is 4096 and your
input is 196,000 tokens, you'll get an error. Always reserve headroom.

### Budgeting heuristic

For a 200K-window agent with `max_tokens=8192`:

| Slice                       | Target budget           | Tactic                      |
|-----------------------------|-------------------------|-----------------------------|
| System prompt + tools       | ≤ 4K tokens (cached)    | Trim, modularize, cache     |
| Conversation history        | ≤ 100K tokens           | Compaction at 80K           |
| Tool results / RAG snippets | ≤ 50K tokens            | Pagination, summary, cap   |
| Output reservation          | 8K tokens               | `max_tokens`                |
| **Headroom**                | **~30K** for spikes     | Don't fill to the brim      |

**Exam framing:** "Quality drops after long sessions" → look at the **tool
results + history** slices first. Those are usually 80% of the bloat.

### The four levers (in order of cost)

| Lever                   | Cost to implement | Magnitude of savings        |
|-------------------------|-------------------|------------------------------|
| Cap tool results        | Trivial           | Often 10–50× on bad cases    |
| Prompt caching          | Small refactor    | 90% off on cached prefix     |
| RAG instead of dump     | Medium            | 10–100× on doc-heavy systems |
| Conversation compaction | Medium            | Linear on long sessions      |

---

## 5.2 Prompt Caching — Ephemeral & Persistent

The exam tests prompt caching aggressively. You will see at least two questions
on it. Internalize the mental model.

### The model

Anthropic offers **prompt caching** that stores a *prefix* of your input
server-side. Subsequent requests with the *same prefix* read from cache:

- **Cached input tokens** cost ~10% of the normal input price.
- **Cache writes** cost ~25% more than normal input (one-time on first request).
- **Cache TTL**: ~5 minutes (ephemeral) by default; 1 hour with the longer
  cache option.

```
First request:   write cost = 1.25× normal input  (warming the cache)
Subsequent:      read cost  = 0.10× normal input  (10× cheaper)
```

### The mechanics

You attach `cache_control` to a content block. Everything **before and
including** that block becomes a cache breakpoint:

```python
SYSTEM = [
    {
        "type": "text",
        "text": LONG_SYSTEM_PROMPT,           # ~10,000 tokens
        "cache_control": {"type": "ephemeral"} # cache up to and including this
    },
]

resp = client.messages.create(
    model="claude-sonnet-4-6", max_tokens=2048,
    system=SYSTEM,
    messages=[{"role": "user", "content": user_input}],
)

# Inspect cache hits/misses:
# resp.usage.cache_creation_input_tokens   ← tokens written this request
# resp.usage.cache_read_input_tokens        ← tokens served from cache
# resp.usage.input_tokens                    ← uncached input tokens
```

### Up to 4 cache breakpoints per request

You can stack breakpoints to cache **layers** of your prompt independently:

```python
SYSTEM = [
    {"type": "text", "text": PERSONA,                           # layer 1: very stable
     "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": TOOL_DOCS,                         # layer 2: changes weekly
     "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": SESSION_CONTEXT,                   # layer 3: per-user
     "cache_control": {"type": "ephemeral"}},
]
```

If `SESSION_CONTEXT` changes per user but `PERSONA` and `TOOL_DOCS` are stable,
two layers stay hot across all users. Without breakpoints, any change in any
layer invalidates the whole cache.

### Where you can put `cache_control`

| Surface           | Cache effect                                              |
|-------------------|-----------------------------------------------------------|
| `system` blocks   | Caches the system prompt prefix                           |
| `tools` array     | Caches tool definitions (declare once, reuse forever)     |
| `messages` blocks | Caches conversation prefix (great for multi-turn agents)  |

### The "stable prefix" rule

Caching only works if **the prefix is byte-identical** across requests. One
flipped field, one rewritten template, and the cache misses. Production
patterns:

- Put **stable** content first (persona, tool defs, system rules).
- Put **variable** content last (the user's current query).
- Don't interpolate timestamps, request IDs, or randomness into the cached
  prefix.
- For multi-turn: cache up to the *last* assistant turn; the new user turn
  appears after the breakpoint.

### Ephemeral vs longer (1-hour) cache

| Variant          | TTL      | Use when                                               |
|------------------|----------|--------------------------------------------------------|
| Ephemeral (default) | ~5 min | High-throughput pipelines (RPS-scale)                  |
| 1-hour cache     | ~1 hour  | Long human conversations, low traffic                  |

Pick **ephemeral** for any system serving more than a few RPS — the prefix
will get re-hit constantly. Pick the **1-hour** variant for assistants where
a single user might come back after a 30-minute pause.

### Common caching mistakes (exam-tested)

| Mistake                                                       | Fix                                            |
|---------------------------------------------------------------|------------------------------------------------|
| Caching with the user's question in the cached prefix         | Move user content after the breakpoint         |
| Embedding `datetime.now()` into system prompt                 | Pass time via the user message or a tool       |
| One `cache_control` at the very end                           | Move it *before* the volatile content          |
| Expecting caching across different `model=` values            | Cache is keyed per-model; you'll miss          |
| Tool definition order changes per request                     | Sort tools deterministically                   |
| Different `system` template per user, only `messages` cached  | Lift shared system content above the divergence|

### A complete cached-agent skeleton

```python
"""
cached_agent.py — multi-turn agent with layered prompt caching.

Cache strategy:
  - Layer 1 (persona, ~3K tokens): cached, breakpoint #1
  - Layer 2 (tool docs, ~5K tokens): cached, breakpoint #2
  - Conversation history: cached up to last assistant turn, breakpoint #3
  - Current user turn: uncached (mandatory; this is the variable)
"""
import os
from anthropic import Anthropic
client = Anthropic()

PERSONA  = """You are a senior cloud architect..."""              # stable
TOOL_DOCS = """### Tools\n\n- search_runbooks: ...\n- ..."""      # weekly-stable

def build_system():
    return [
        {"type": "text", "text": PERSONA,
         "cache_control": {"type": "ephemeral"}},                  # bp #1
        {"type": "text", "text": TOOL_DOCS,
         "cache_control": {"type": "ephemeral"}},                  # bp #2
    ]

def chat(history, user_msg):
    """history: list of past {role, content} turns; user_msg: current input."""
    if history:
        # Mark the LAST item in history as the cache breakpoint for the convo prefix.
        history = history[:-1] + [_with_cache(history[-1])]        # bp #3
    messages = history + [{"role": "user", "content": user_msg}]    # uncached tail

    resp = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=2048,
        system=build_system(), messages=messages,
    )
    # Quick observability — log cache health per request
    u = resp.usage
    print(f"cache_read={u.cache_read_input_tokens} "
          f"cache_write={u.cache_creation_input_tokens} "
          f"uncached={u.input_tokens}")
    return resp

def _with_cache(turn):
    """Wrap a string-content turn so we can attach cache_control."""
    content = turn["content"]
    if isinstance(content, str):
        content = [{"type": "text", "text": content}]
    content[-1]["cache_control"] = {"type": "ephemeral"}
    return {"role": turn["role"], "content": content}
```

---

## 5.3 The CALM Framework

Anthropic's mnemonic for **context lifecycle management**. Every CCA-F form has
one CALM-tagged question.

| Letter | Stage          | What you do                                                |
|--------|----------------|------------------------------------------------------------|
| **C**  | **C**urate     | Decide what should enter the window in the first place    |
| **A**  | **A**ttribute  | Label sources so the model (and you) can audit provenance  |
| **L**  | **L**imit      | Cap inputs (tool results, RAG, history) at known budgets   |
| **M**  | **M**aintain   | Compact, summarize, evict as the conversation grows        |

### CALM in practice

```python
# CURATE — pull only relevant docs, not everything
docs = vector_store.top_k(query, k=5)

# ATTRIBUTE — every snippet labeled with source
context = "\n\n".join(f"[doc:{d.id}] {d.text}" for d in docs)

# LIMIT — cap before insertion
if len(context) > MAX_CONTEXT_TOKENS:
    context = truncate(context, MAX_CONTEXT_TOKENS)

# MAINTAIN — compact at threshold
if estimate_tokens(history) > 80_000:
    history = compact(history)
```

### Why CALM beats "just dump it all in"

- **Curate**: irrelevant context dilutes attention and pays for nothing.
- **Attribute**: when the model cites or contradicts a source, you can trace
  it. Hallucination triage is impossible without source labels.
- **Limit**: production systems should *never* allow arbitrary growth — every
  variable input needs a budget.
- **Maintain**: long conversations without compaction degrade after ~50K tokens
  even on 200K-window models.

### CALM exam framings

- "User reports the assistant cites pages that don't exist." → likely
  **Attribute** failure (no source labels) and/or **Curate** failure
  (irrelevant docs retrieved).
- "Quality drops after 100+ tool calls in one session." → **Maintain** failure
  (no compaction).
- "RAG occasionally pulls in 50KB of context." → **Limit** failure (no cap on
  retrieved context).

---

## 5.4 Multi-Turn Conversation Design

Long conversations are where context-management discipline pays off — and
where it fails.

### The naive pattern (broken at scale)

```python
messages = []
while True:
    user = input("> ")
    messages.append({"role": "user", "content": user})
    resp = client.messages.create(model="...", messages=messages, ...)
    messages.append({"role": "assistant", "content": resp.content})
```

Failure modes:
- Every turn re-sends every prior turn — cost grows quadratically.
- After ~50K tokens, lost-in-the-middle kicks in.
- One huge tool result poisons the entire rest of the session.

### The production pattern

```python
"""
multiturn.py — production multi-turn loop with caching, compaction, and tool-result capping.
"""
import json
from anthropic import Anthropic
client = Anthropic()

MAX_HISTORY_TOKENS = 80_000
TOOL_RESULT_MAX_BYTES = 6_000

def estimate_tokens(messages):
    # Rough estimate; for production use tiktoken/anthropic tokenizer.
    return sum(len(json.dumps(m)) // 4 for m in messages)

def cap_tool_result(result_str):
    if len(result_str) <= TOOL_RESULT_MAX_BYTES:
        return result_str
    # Truncate with a sentinel so the model knows it was cut.
    head = result_str[:TOOL_RESULT_MAX_BYTES - 200]
    return head + f"\n\n[truncated {len(result_str) - len(head)} bytes — call again with pagination]"

def compact(history):
    """
    Summarize old turns into a single 'summary' message; keep the last K turns verbatim.
    Production: use a cheap model (Haiku) to write the summary.
    """
    keep_last = 6
    old, recent = history[:-keep_last], history[-keep_last:]
    if not old:
        return history

    summary = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="Summarize the conversation below in <= 400 tokens. Preserve decisions, "
               "tools called, and any user-provided constraints.",
        messages=[{"role": "user", "content": json.dumps(old)}],
    ).content[0].text

    return [{"role": "user", "content":
             f"<conversation_summary>{summary}</conversation_summary>"}] + recent

def turn(history, user_msg, system, tools):
    if estimate_tokens(history) > MAX_HISTORY_TOKENS:
        history = compact(history)                           # MAINTAIN

    history = history + [{"role": "user", "content": user_msg}]
    resp = client.messages.create(
        model="claude-sonnet-4-6", max_tokens=2048,
        system=system, tools=tools, messages=history,
    )
    history.append({"role": "assistant", "content": resp.content})

    while resp.stop_reason == "tool_use":
        results = []
        for blk in resp.content:
            if blk.type == "tool_use":
                raw = run_tool(blk.name, blk.input)           # your tool runner
                results.append({"type": "tool_result",
                                "tool_use_id": blk.id,
                                "content": cap_tool_result(raw)})  # LIMIT
        history.append({"role": "user", "content": results})
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=2048,
            system=system, tools=tools, messages=history,
        )
        history.append({"role": "assistant", "content": resp.content})

    return history, "".join(b.text for b in resp.content if b.type == "text")
```

### Compaction strategies

| Strategy                         | When                                       | Notes                                      |
|----------------------------------|--------------------------------------------|--------------------------------------------|
| **Sliding window**               | Token-bounded chats with no long-range refs| Drop oldest until under threshold          |
| **Summarize-and-replace**        | Long agent sessions                        | Replace prefix with summary; keep last K   |
| **Hierarchical summary**         | Very long sessions (1M+ tokens lifetime)   | Summary of summaries; tree of context      |
| **Selective retention**          | Long-tail sessions                         | Score turns; keep top-N by relevance       |

> **Exam gotcha:** "Switch to a model with a larger context window" is rarely
> the right answer to a long-conversation problem. The structural fix is
> compaction + caching.

### Tool-result poisoning

A single 50KB tool result lives in the context window for the rest of the
session. Mitigations:

- Cap tool result size at the boundary (as in `cap_tool_result` above).
- Have a "summarize this large output" step before storing in history.
- For tools that return huge data, return a *reference* (file path, URL) the
  agent can fetch a slice of via a second tool.

---

## 5.5 RAG — When and How

RAG is *the* canonical answer when the question is "Claude needs knowledge it
doesn't have, but I can't fit my whole corpus in the context window."

### The core pattern

```
user query
   │
   ▼
embed(query) ───► vector store ───► top-k passages
                                        │
                                        ▼
                  build prompt with retrieved passages + query
                                        │
                                        ▼
                              messages.create(...)
```

### When RAG beats long context

| Need                                     | RAG | Long context |
|------------------------------------------|-----|--------------|
| 10-page manual referenced rarely         |  ✓  |              |
| Whole codebase, occasional Q&A           |  ✓  |              |
| 1,000 PDFs of company docs               |  ✓  |              |
| Single ~50KB document referenced often   |     |  ✓ (cache it)|
| Tight reasoning across whole corpus      |     |  ✓ if it fits|
| Source-attribution required              |  ✓  | (also fine)  |

### Five RAG sub-patterns the exam mentions

1. **Vanilla RAG** — embed + top-k + stuff into prompt.
2. **Hybrid RAG** — keyword (BM25) + dense embeddings; merge top results.
3. **Reranking** — pull top 25 with embeddings; rerank with a cross-encoder
   to get top 5.
4. **Contextual retrieval** — prepend a contextualized summary to each chunk
   before embedding (Anthropic's published variant).
5. **Tool-driven retrieval** — expose `search_kb` as a tool; agent decides
   when and how to retrieve, possibly multiple times.

### Tool-driven retrieval (the agentic answer)

```python
# Instead of pre-stuffing context, give the agent a search tool.
TOOLS = [{
    "name": "search_kb",
    "description": "Search the knowledge base. Returns up to 5 relevant snippets with source IDs.",
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string"}, "k": {"type": "integer", "minimum": 1, "maximum": 5}},
        "required": ["query"],
    },
}]

def run_search_kb(args):
    hits = vector_store.search(args["query"], k=args.get("k", 5))
    return json.dumps([{"id": h.id, "text": h.text[:1000], "score": h.score} for h in hits])
```

The agent decides when to call `search_kb`, can refine queries, and only burns
tokens for the *relevant* hits. This is the **default RAG pattern in agentic
systems** — it scales better than monolithic stuffing and makes attribution
trivial.

### RAG anti-patterns

| Anti-pattern                                              | Fix                                          |
|-----------------------------------------------------------|----------------------------------------------|
| Stuffing 50 passages into context "to be safe"            | Top-3 to 5; rerank if precision matters      |
| No source attribution on retrieved snippets               | Label every snippet with `[doc:id]`          |
| Retrieving on every turn even when not needed             | Tool-driven retrieval; let agent decide       |
| Embeddings only on raw chunks (no context)                | Use contextual retrieval                     |
| Recreating embeddings for unchanged docs                  | Persist embeddings; recompute on doc update  |

### Retrieval evaluation

Like prompts (Domain 4), retrieval needs **labeled evals**:

- **Recall@k** — does the top-k contain the gold passage?
- **MRR** — mean reciprocal rank of the gold passage.
- End-to-end accuracy on the downstream task.

If retrieval recall is high but task accuracy is low, the prompt is the
problem. If recall is low, retrieval is the problem. Diagnose at the right
layer.

---

## 5.6 Reliability Patterns

The exam includes "reliability" in this domain because context choices drive
reliability. The patterns:

### 5.6.1 Idempotency keys for tool calls

Already covered in Domain 2 — repeat for context. Idempotency keys live in
the **conversation history**: when the agent retries, the same key reaches
the tool. This requires keys to be deterministic, not random per-turn.

### 5.6.2 Checkpointing long agent sessions

For sessions that span hours or days, periodically snapshot:

```python
import pickle, time

def checkpoint(session_id, history, tools_state):
    path = f"sessions/{session_id}-{int(time.time())}.pkl"
    with open(path, "wb") as f:
        pickle.dump({"history": history, "tools_state": tools_state}, f)

def restore(session_id):
    latest = sorted(glob.glob(f"sessions/{session_id}-*.pkl"))[-1]
    return pickle.load(open(latest, "rb"))
```

Checkpoints let you resume after a crash without losing the agent's plan or
prior tool side-effects.

### 5.6.3 Graceful degradation

If a tool times out, return `{"status": "degraded", "fallback": ...}` instead
of failing. The model can route around it. This is the **circuit-breaker**
pattern at the tool layer.

### 5.6.4 Token budget circuit breakers

```python
if estimate_cost(messages) > MAX_PER_REQUEST_USD:
    raise BudgetExceeded(f"request would cost ${estimated:.2f}")
```

Production agents need a hard cap. Without it, one runaway loop (Domain 1
failure mode) drains the cost budget.

### 5.6.5 Observability tags

Every Anthropic API call accepts `metadata.user_id` and supports custom
tracing. Tag every request with session ID, request ID, agent role, and
prompt version — without these, debugging long sessions is impossible.

```python
client.messages.create(
    ...,
    metadata={"user_id": session_id},
)
```

---

## 5.7 Architecture Decision Frameworks

### Framework A — "Where should this content live?"

```
Is it stable across requests?
    YES → cached system prompt (Domain 4)
Is it stable across this user's session?
    YES → cached message prefix
Is it variable per request, but small (<2K tokens)?
    YES → uncached message tail
Is it variable, large, and not always needed?
    YES → tool-driven retrieval (RAG)
Is it the user's current ask?
    → uncached final user message
```

### Framework B — "How do I shrink the context window?"

```
1. Cap tool results (TRIVIAL FIRST WIN)
2. Add prompt caching to the stable prefix
3. Move high-volume content to RAG (tool-driven)
4. Compact conversation history at threshold
5. Only THEN consider a larger-context model
```

### Framework C — "Why is quality dropping in long sessions?"

| Symptom                                       | Likely cause              | Fix                              |
|-----------------------------------------------|---------------------------|----------------------------------|
| Model forgets early context                   | Lost-in-the-middle        | Compact + restate near question  |
| Cites things that don't exist                 | No source attribution     | CALM Attribute                   |
| Cost explodes mid-session                     | History + tool-result bloat | Cap + compact + cache            |
| Latency creeps up                             | Cached prefix invalidated | Audit `cache_read` metric        |
| Agent re-asks for things you told it          | History truncated wrongly | Selective retention not sliding window |

---

## 5.8 Practice MCQs (Domain 5)

---

**Q1.** Your customer-support assistant has a 12,000-token system prompt that
rarely changes, plus per-user session context that varies. Cost is dominated
by the system prompt. Which is the highest-ROI change?

A. Switch to Haiku 4.5 for cost.
B. Add `cache_control: ephemeral` after the stable system prompt so it caches
   across requests; keep variable session content after the breakpoint.
C. Move the system prompt into the user message.
D. Reduce `max_tokens`.

---

**Q2.** Your agent's tool returns a 200KB JSON dump on a `list_users` call.
After this turn, **the agent's quality degrades sharply** for the rest of the
session. The MOST direct fix is:

A. Use a model with a 1M context window.
B. Cap tool results at the boundary (paginate; truncate with a sentinel; or
   summarize before storing).
C. Increase temperature.
D. Disable the tool.

---

**Q3.** A team built a RAG system that retrieves 25 passages and stuffs all of
them into context. Recall is high, but **the model often hallucinates citations**
that don't match the retrieved sources. Which fix addresses the root cause?

A. Retrieve only top-5 with reranking, and **label each snippet with its source
   ID** so the model can attribute quotes correctly.
B. Switch to extended thinking.
C. Increase the embedding model dimension.
D. Add more retrieved passages to "average out" the hallucinations.

---

**Q4.** A multi-turn assistant works great for the first 30 turns, then
**gradually slows down and hallucinates earlier facts**. Costs are also rising
linearly. The architectural fix is:

A. Use a model with a larger context window so all turns fit.
B. Implement conversation compaction: summarize old turns with a cheap model,
   keep the last K verbatim.
C. Set `temperature=0`.
D. Reset the conversation every 30 turns.

---

**Q5.** Your team's prompt cache hit rate is **near zero**, even though the
system prompt is constant. Inspecting the requests, you notice each request's
system prompt has `f"Today is {datetime.utcnow().isoformat()}"` interpolated
in. The fix is:

A. Switch to the 1-hour cache.
B. Move the timestamp **out** of the cached system prefix — pass it through
   a tool or in the user message instead.
C. Use multiple `cache_control` breakpoints.
D. Disable caching to remove the variability.

---

**Q6.** You're building an internal Q&A assistant over a 1,000-PDF compliance
library. Most queries reference 1–2 documents. Which architecture is best?

A. Concatenate all 1,000 PDFs into the system prompt; rely on the 200K context.
B. RAG with embeddings + reranking; expose retrieval as a tool the agent calls
   when needed.
C. Fine-tune a model on the corpus.
D. Use computer-use to navigate a PDF reader.

---

**Q7.** Which CALM stage is responsible for **labeling each retrieved snippet
with a source ID** so the model and humans can audit provenance?

A. Curate
B. Attribute
C. Limit
D. Maintain

---

**Q8.** A long-running autonomous agent occasionally crashes mid-session,
losing all progress. The team wants to **resume after a crash**. The best
mechanism is:

A. Periodic checkpointing of the conversation history + tools state to disk;
   restore the latest snapshot on crash.
B. A larger context window.
C. More retries on the API call.
D. A monitoring dashboard.

---

**Q9.** A team adds three layers of `cache_control` to their request: persona,
tool docs, and per-user context. After deployment, cache hit rates are great
on persona but **terrible on per-user context**. The likely cause is:

A. Cache breakpoints are mutually exclusive.
B. Per-user context is, by definition, not shared across users — only that
   user's repeat requests will hit. Per-user caching is mainly a multi-turn
   optimization within one user's session.
C. Three breakpoints exceed the cap of 4 cache breakpoints.
D. The 1-hour cache must be enabled.

---

**Q10.** Your tool-driven RAG agent calls `search_kb` 14 times in one
session, each returning 5 snippets that the model then ignores in subsequent
turns. The most direct optimization is:

A. Add a `compact_search_results` step that, after each batch, summarizes the
   retrieved snippets into a brief and drops the raw snippets from later
   turns.
B. Disable `search_kb`.
C. Increase the embedding dimension.
D. Switch to a 1M-context model.

---

### Answers & Rationale

| Q  | Ans | Why                                                                                            |
|----|-----|------------------------------------------------------------------------------------------------|
| 1  | B   | Caching the stable prefix is the highest-ROI lever for repeated prompts.                       |
| 2  | B   | Cap at the boundary; tool-result bloat is the most common context-quality killer.              |
| 3  | A   | Smaller, higher-precision context with attribution; quantity isn't quality.                    |
| 4  | B   | Compaction is the structural answer to long-session degradation.                               |
| 5  | B   | Volatile content in cached prefix kills the cache; move it after the breakpoint.               |
| 6  | B   | Sparse-access corpus = RAG; agent-driven retrieval scales and attributes naturally.            |
| 7  | B   | CALM Attribute is the source-labeling stage.                                                    |
| 8  | A   | Checkpointing is the recovery primitive.                                                        |
| 9  | B   | Per-user cache only helps within one user's session, not across users.                          |
| 10 | A   | Compaction of accumulated retrieval results — the long-session counterpart to tool-result cap. |

---

## 5.9 Mini-Lab — A Cached, Compacting, RAG-Backed Assistant

**Goal:** A `chat(session_id, user_msg) -> str` function that:

1. Has a layered cached system prompt (persona + tool docs).
2. Exposes a `search_kb` tool against an in-memory vector store.
3. Caps tool results at 6KB.
4. Compacts conversation when token estimate exceeds 60K.
5. Logs cache hit/miss metrics per request.
6. Persists session history per `session_id` to disk; restores on next call.

**Skeleton:**

```python
"""
assistant.py — production-shaped multi-turn agent with caching, capping, compaction, and RAG.
"""
import os, json, pickle, glob, time
from anthropic import Anthropic

client = Anthropic()
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

PERSONA = """You are a senior cloud architect. ..."""               # ~3K tokens
TOOL_DOCS = """### Tools\n- search_kb: ...\n"""                     # ~1K tokens

VECTOR_STORE = ...   # your favorite (Chroma, Qdrant, in-memory dict)

TOOLS = [{
    "name": "search_kb",
    "description": "Search the knowledge base; returns up to 5 snippets w/ source IDs.",
    "input_schema": {"type": "object",
                     "properties": {"query": {"type": "string"},
                                    "k": {"type": "integer", "minimum": 1, "maximum": 5}},
                     "required": ["query"]},
}]

MAX_HISTORY_TOKENS = 60_000
TOOL_RESULT_CAP_BYTES = 6_000

def _system():
    return [
        {"type": "text", "text": PERSONA, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": TOOL_DOCS, "cache_control": {"type": "ephemeral"}},
    ]

def _est_tokens(messages):
    return sum(len(json.dumps(m)) // 4 for m in messages)

def _cap(s):
    if len(s) <= TOOL_RESULT_CAP_BYTES:
        return s
    return s[:TOOL_RESULT_CAP_BYTES - 200] + f"\n[truncated; call again w/ refined query]"

def _run_tool(name, args):
    if name == "search_kb":
        hits = VECTOR_STORE.search(args["query"], k=args.get("k", 5))
        return json.dumps([{"id": h.id, "text": h.text[:800]} for h in hits])
    return json.dumps({"error": f"unknown {name}"})

def _compact(history):
    if len(history) <= 6:
        return history
    old, recent = history[:-6], history[-6:]
    summary = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=1024,
        system="Summarize the conversation in <=300 tokens. Preserve decisions, "
               "search results, and constraints.",
        messages=[{"role": "user", "content": json.dumps(old)}],
    ).content[0].text
    return [{"role": "user", "content": f"<summary>{summary}</summary>"}] + recent

def _save(session_id, history):
    pickle.dump(history, open(f"{SESSIONS_DIR}/{session_id}.pkl", "wb"))

def _load(session_id):
    path = f"{SESSIONS_DIR}/{session_id}.pkl"
    return pickle.load(open(path, "rb")) if os.path.exists(path) else []

def chat(session_id: str, user_msg: str) -> str:
    history = _load(session_id)

    if _est_tokens(history) > MAX_HISTORY_TOKENS:
        history = _compact(history)

    history.append({"role": "user", "content": user_msg})

    while True:
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=2048,
            system=_system(), tools=TOOLS, messages=history,
        )
        u = resp.usage
        print(f"[{session_id}] cache_read={u.cache_read_input_tokens} "
              f"cache_write={u.cache_creation_input_tokens} "
              f"in={u.input_tokens} out={u.output_tokens}")

        history.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "tool_use":
            results = []
            for blk in resp.content:
                if blk.type == "tool_use":
                    raw = _run_tool(blk.name, blk.input)
                    results.append({"type": "tool_result",
                                    "tool_use_id": blk.id,
                                    "content": _cap(raw)})
            history.append({"role": "user", "content": results})
            continue

        _save(session_id, history)
        return "".join(b.text for b in resp.content if b.type == "text")
```

**Stretch goals:**
- Switch in-memory vector store for a real one (Chroma, Qdrant, or pgvector).
- Add reranking (cross-encoder) on top-25 → top-5.
- Add a 1-hour cache layer for the persona; ephemeral for tool docs.
- Add a per-session cost budget; raise `BudgetExceeded` if a turn would
  push above the cap.

---

## 5.10 Domain 5 Cheatsheet (flashcard-ready)

```
══════════════════════════════════════════════════════════════════════════
DOMAIN 5 — CONTEXT MANAGEMENT & RELIABILITY    (15%)
══════════════════════════════════════════════════════════════════════════

CORE FRAME
  Context window = SCARCE, BILLABLE working memory.
  Every token costs money on every turn AND dilutes attention.
  "Use a bigger context window" is rarely the right answer.

WINDOW SLICES (200K example)
  system prompt + tools     ≤  4K  (CACHE)
  conversation history      ≤ 100K (compact at 80K)
  tool results / RAG        ≤  50K (cap, paginate, summarize)
  output reservation         ~ 8K  (max_tokens)
  headroom                  ~ 30K

THE FOUR LEVERS (in order)
  1. Cap tool results        — trivial, biggest wins
  2. Prompt caching          — small refactor, 10× off prefix
  3. RAG (tool-driven)       — for sparse-access corpora
  4. Conversation compaction — for long sessions

PROMPT CACHING
  cache_control: ephemeral (~5 min) | longer (~1 hr)
  Up to 4 breakpoints
  Read = 0.10×, Write = 1.25× normal input
  STABLE prefix first, VARIABLE content last
  Caches: system blocks, tools, message prefix
  Per-model key — don't expect cross-model hits
  Inspect resp.usage.cache_read_input_tokens / cache_creation_input_tokens

CACHING ANTI-PATTERNS
  ✗ datetime.now() in cached prefix
  ✗ user query inside cached prefix
  ✗ tool order non-deterministic
  ✗ different system per request, expecting tail caching
  ✗ caching across model variants

CALM
  C urate    — pull only relevant
  A ttribute — label sources (avoid hallucinated citations)
  L imit     — cap inputs (history, RAG, tool results)
  M aintain  — compact, summarize, evict

MULTI-TURN PRODUCTION PATTERN
  - cap tool_result at boundary
  - compact when est_tokens > threshold
  - keep last K verbatim, summarize older
  - cache up to last assistant turn
  - persist session for crash recovery

RAG SUB-PATTERNS
  vanilla     embed + top-k + stuff
  hybrid      keyword + dense, merge
  rerank      retrieve top-25, rerank to top-5
  contextual  prepend chunk-summary before embedding
  tool-driven agent calls search_kb when needed (preferred for agentic)

RAG ANTI-PATTERNS
  ✗ stuffing 25 passages "to be safe"
  ✗ unsourced snippets (Attribute fail)
  ✗ retrieve every turn even when unused
  ✗ recompute embeddings on unchanged docs

RELIABILITY PATTERNS
  Idempotency keys → deterministic, persisted in history
  Checkpointing    → snapshot history+state for resume
  Graceful degrade → tool returns status:"degraded" instead of timing out
  Cost circuit     → MAX_PER_REQUEST_USD before .create()
  Observability    → metadata.user_id, prompt version tag, request id

DECISION QUICK-CHOOSER
  stable across requests   → cached system prompt
  stable per session       → cached message prefix
  variable + sparse access → tool-driven RAG
  long conversation        → compaction + last-K retention
  long output / reasoning  → reserve max_tokens, don't fill window
  citations needed         → CALM Attribute (label every source)
  long-running agent       → checkpointing + cost circuit breaker

EXAM TRAPS (instant-wrong)
  ✗ "Switch to a bigger-context model" (not the architectural answer)
  ✗ "Add more passages" to fix RAG hallucination
  ✗ Caching with volatile content in the prefix
  ✗ No tool-result cap → context poisoning
  ✗ No compaction in long sessions
  ✗ Skipping source attribution in RAG
  ✗ Re-creating embeddings every time
══════════════════════════════════════════════════════════════════════════
```

---

> All 5 domains complete. The next file is the **4-week study plan**, weighted
> by domain percentage and ordered to build the right intuitions for the exam.
