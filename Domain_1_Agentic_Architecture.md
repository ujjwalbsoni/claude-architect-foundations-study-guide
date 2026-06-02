# Domain 1: Agentic Architecture & Orchestration (27% of CCA-F)

> The highest-weighted domain. Roughly **16 of 60 questions**. Master this and you've banked
> nearly a third of the exam. Distractors here are very plausible — the exam tests whether
> you pick the right *architecture* under production constraints, not whether you know
> definitions.

---

## 1.0 Mental Model — What Is an "Agent"?

Anthropic's working definition (used throughout the exam):

> An **agent** is an LLM that uses tools in a **loop** to accomplish a goal,
> deciding for itself when it is done.

Four ingredients, all required:

| Ingredient        | What it is                                                         | Failure if missing                       |
|-------------------|--------------------------------------------------------------------|------------------------------------------|
| LLM               | The reasoning core (Claude)                                        | Just an API call                         |
| Tools             | Side-effecting functions the model can invoke                      | A chatbot, not an agent                  |
| Loop              | Re-prompt with tool results until model stops                      | One-shot tool use, not autonomous        |
| Termination logic | `stop_reason == "end_turn"` or budget exhausted                    | Infinite loop / runaway cost             |

A **workflow** (deterministic, hard-coded sequence) is *not* an agent. The exam will
plant distractors that look agentic but are actually workflows. The discriminator is
**who decides the next step** — the code (workflow) or the model (agent)?

### When to use an agent vs a workflow (exam-critical tradeoff)

| Use a **workflow** when…                              | Use an **agent** when…                                  |
|-------------------------------------------------------|---------------------------------------------------------|
| Steps are known in advance                            | Steps depend on intermediate results                    |
| Cost/latency must be predictable                      | Some flexibility in cost/latency is acceptable          |
| Failure modes are bounded                             | Open-ended exploration is required                      |
| Auditability is paramount (e.g. regulated transfers)  | Task variety dwarfs your ability to enumerate paths     |

Memorize: **agents trade predictability for capability**. If the question stem
emphasizes SLAs, regulated workflows, or determinism — pick the workflow.

---

## 1.1 The Agentic Loop — Canonical Implementation

Every CCA-F question about loops, tool errors, or termination assumes you can mentally
run this code. Internalize it.

```python
"""
agentic_loop.py — the canonical Claude tool-use loop.

WHY this shape:
  - We must re-send the FULL conversation each turn (Claude is stateless).
  - We MUST append the assistant's tool_use turn AND the tool_result turn,
    in order, before re-prompting. Skipping either is the #1 cause of
    "unexpected role" 400s.
  - Termination is driven by stop_reason, NOT by counting tool calls.
"""

import os
import json
from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ---------- 1. Tool catalog -------------------------------------------------
# Tool SCHEMAS are sent to Claude. Tool IMPLEMENTATIONS run in your process.
TOOLS = [
    {
        "name": "get_weather",
        "description": "Get current weather for a city. Use only for cities, not regions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "City name, e.g. 'Tokyo'"},
                "units": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["city"],
        },
    },
    {
        "name": "get_time",
        "description": "Get current local time for an IANA timezone.",
        "input_schema": {
            "type": "object",
            "properties": {"tz": {"type": "string"}},
            "required": ["tz"],
        },
    },
]


def execute_tool(name: str, args: dict) -> str:
    """Dispatch to the actual implementation. Return a STRING (or JSON string)."""
    if name == "get_weather":
        # Real impl would call an API. Mocked here.
        return json.dumps({"city": args["city"], "temp": 22, "units": args.get("units", "celsius")})
    if name == "get_time":
        return json.dumps({"tz": args["tz"], "iso": "2026-06-01T12:00:00"})
    # CRITICAL: never raise. Return an error string the model can react to.
    return json.dumps({"error": f"unknown tool {name}"})


# ---------- 2. The loop -----------------------------------------------------
def run_agent(user_prompt: str, max_iters: int = 10) -> str:
    """
    Run the agent until stop_reason == 'end_turn' or budget exhausted.

    max_iters is a SAFETY belt, not a feature. A well-designed agent should
    almost always terminate naturally; hitting the cap means your prompt or
    tools have a bug.
    """
    messages = [{"role": "user", "content": user_prompt}]

    for iteration in range(max_iters):
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            tools=TOOLS,
            messages=messages,
        )

        # Always append the assistant turn FIRST. Failing to do this and
        # then sending a tool_result is the #1 400 error in production.
        messages.append({"role": "assistant", "content": response.content})

        # Natural termination: Claude said it is done.
        if response.stop_reason == "end_turn":
            # Extract final text block(s)
            return "".join(b.text for b in response.content if b.type == "text")

        # If Claude wants to use tools, stop_reason is "tool_use".
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                try:
                    output = execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,   # MUST match the tool_use id
                        "content": output,
                    })
                except Exception as e:
                    # Tools that crash the loop are bugs. Surface the error
                    # to the model so it can recover or apologize.
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": f"ERROR: {e}",
                        "is_error": True,
                    })

            # All tool_result blocks for one assistant turn go in ONE user message.
            messages.append({"role": "user", "content": tool_results})
            continue

        # Other stop_reasons: max_tokens, stop_sequence, refusal.
        # max_tokens with mid-tool_use is salvageable by re-prompting; here we bail.
        return f"[stopped: {response.stop_reason}]"

    raise RuntimeError(f"Agent exceeded {max_iters} iterations — investigate.")


if __name__ == "__main__":
    print(run_agent("What's the weather and time in Tokyo?"))
```

### Things the exam will test about this loop

1. **Stateless API.** Every turn re-sends the entire `messages` array. There is no
   server-side conversation state. (Compactly: "Claude doesn't remember.")
2. **Stop reasons.** `end_turn`, `tool_use`, `max_tokens`, `stop_sequence`, `refusal`.
   Only `tool_use` continues the loop; everything else terminates it.
3. **Tool result placement.** `tool_result` blocks live in a `user` message, not an
   `assistant` message, and their `tool_use_id` must match.
4. **Parallel tool calls.** A single assistant turn can emit *multiple* `tool_use`
   blocks. You must execute them all and return all `tool_result`s in one user message
   in the same order — failing to is a common production bug.
5. **Tool errors are data, not exceptions.** Use `is_error: true` and let the model
   recover. Crashing the loop denies the model agency.

---

## 1.2 Task Decomposition

The exam frames decomposition as a *design choice*, not a technique. Three modes:

| Mode                    | Decider          | Cost     | Best for                                    |
|-------------------------|------------------|----------|---------------------------------------------|
| **Static decomposition**| Engineer ahead-of-time | $       | Stable, well-understood pipelines           |
| **Planner-first**       | Claude (one-shot plan, then exec) | $$  | Bounded tasks with predictable shape        |
| **Dynamic / agentic**   | Claude (decides each step inside the loop) | $$$ | Open-ended research, debugging, browsing    |

### Heuristics (memorize)

- If you can write the DAG with a whiteboard, use **static**.
- If the DAG depends on the user's input but is shallow, use **planner-first**.
- If the DAG depends on intermediate tool outputs, use **dynamic**.
- **Decomposition cost grows with depth.** Each level of subagent ≈ 2–5× tokens.

```python
# Planner-first decomposition (cheap, predictable)
PLANNER_SYSTEM = """You are a planner. Output ONLY a JSON array of steps.
Each step has: {"id": int, "task": str, "depends_on": [int]}.
Do NOT execute anything."""

def plan(goal: str) -> list[dict]:
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",   # planning is cheap; use Haiku
        max_tokens=1024,
        system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": goal}],
    )
    return json.loads(resp.content[0].text)
```

> **Exam gotcha:** If asked "where should the *plan* be generated?" — the answer is
> almost always **a smaller/cheaper model** (Haiku) for planning, with the larger
> model (Opus) for execution of complex steps. Inversion is a distractor.

---

## 1.3 Hub-and-Spoke Orchestration

The dominant multi-agent pattern on the exam.

```
                  ┌─────────────┐
                  │ Orchestrator│   ← maintains the master plan & state
                  │   (Opus)    │
                  └──┬──┬──┬────┘
           dispatch  │  │  │  dispatch
                    ▼  ▼  ▼
              ┌──────┐ ┌──────┐ ┌──────┐
              │ Sub A│ │ Sub B│ │ Sub C│  ← isolated context windows
              └──────┘ └──────┘ └──────┘
```

### Why hub-and-spoke (and not peer-to-peer)?

| Property              | Hub-and-spoke                       | Peer-to-peer                       |
|-----------------------|-------------------------------------|-------------------------------------|
| Coordination overhead | O(N) — orchestrator routes          | O(N²) — every agent talks to every  |
| Determinism           | High (single planner)               | Low (race conditions, deadlocks)    |
| Debuggability         | One trace                           | N×N traces                          |
| Failure blast radius  | Bounded to one branch               | Cascades                            |
| Best fit              | Most production agentic systems     | Negotiation/simulation research     |

**The exam answer is almost always hub-and-spoke.** Pick peer-to-peer only when the
scenario explicitly says agents must *negotiate* without a coordinator.

### Reference implementation

```python
"""
orchestrator.py — hub-and-spoke with isolated subagent contexts.

Key design choices (exam-relevant):
 1. Each subagent gets its OWN messages array. Their context never bleeds
    into siblings — this is the whole point of the pattern.
 2. The orchestrator only sees subagent SUMMARIES, not raw transcripts,
    to preserve its own context budget.
 3. Subagents run in parallel where possible (concurrent.futures).
"""

import concurrent.futures as cf
from anthropic import Anthropic
client = Anthropic()

SUBAGENT_SYSTEM = """You are a focused research subagent.
Investigate ONE topic. Return a 5-bullet summary at the end.
Use the provided tools. Do not delegate further."""

def run_subagent(topic: str, tools: list) -> str:
    """Each subagent is a self-contained agentic loop."""
    messages = [{"role": "user", "content": f"Research: {topic}"}]
    for _ in range(8):                        # cap per subagent
        resp = client.messages.create(
            model="claude-sonnet-4-6",        # Sonnet for workers; Opus for hub
            max_tokens=2048,
            system=SUBAGENT_SYSTEM,
            tools=tools,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "end_turn":
            return "".join(b.text for b in resp.content if b.type == "text")
        # ... tool-handling identical to canonical loop ...
    return "[subagent timeout]"


ORCH_SYSTEM = """You are an orchestrator. Decompose the user's research goal
into 3–5 INDEPENDENT subtopics. Return JSON: {"subtopics": [str, ...]}.
After receiving subagent summaries, synthesize a final answer."""

def orchestrate(goal: str, tools: list) -> str:
    # Phase 1: planning
    plan_resp = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=1024,
        system=ORCH_SYSTEM,
        messages=[{"role": "user", "content": goal}],
    )
    plan = json.loads(plan_resp.content[0].text)

    # Phase 2: parallel fan-out (the "spoke" part)
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(run_subagent, t, tools): t for t in plan["subtopics"]}
        summaries = {futures[f]: f.result() for f in cf.as_completed(futures)}

    # Phase 3: synthesis (hub re-engaged with summaries only — NOT raw traces)
    synthesis_input = "\n\n".join(f"## {k}\n{v}" for k, v in summaries.items())
    final = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=ORCH_SYSTEM,
        messages=[
            {"role": "user", "content": goal},
            {"role": "assistant", "content": json.dumps(plan)},
            {"role": "user", "content": f"Subagent summaries:\n{synthesis_input}"},
        ],
    )
    return "".join(b.text for b in final.content if b.type == "text")
```

### Architectural principles encoded above

- **Context isolation.** Subagent messages never appear in the orchestrator's window.
  This is the *defining feature* of hub-and-spoke. If you let raw traces bleed up,
  you have re-implemented a single agent with extra steps.
- **Model tiering.** Opus orchestrates, Sonnet works, Haiku plans — match capability
  to the cognitive load of the role.
- **Parallelism is opt-in.** Only fan out subtasks that are *independent*. Dependent
  steps must be sequential (the orchestrator threads results through).

---

## 1.4 Subagent Coordination Patterns

Beyond plain hub-and-spoke, the exam covers four sub-patterns:

### 1.4.1 Parallel fan-out (independent work)

Launch N subagents at once, await all, synthesize. Used in Claude Code's research
agent. Latency ≈ slowest subagent. Cost = sum.

### 1.4.2 Sequential pipeline (dependent work)

`A → B → C`, where B reads A's output. Cheaper than parallel but has no parallelism
gain. Used for "draft → critique → revise" chains.

### 1.4.3 Critic / evaluator pair

```python
draft = generator_agent(task)
for _ in range(MAX_ROUNDS):
    critique = critic_agent(draft)
    if critique["status"] == "approved":
        return draft
    draft = generator_agent(task, prior=draft, critique=critique)
```

Critic runs as a separate subagent with a *different* system prompt to reduce
sycophancy. The exam will ask why we don't just have the generator self-critique —
answer: the same context produces correlated errors; an isolated critic produces
*independent* errors.

### 1.4.4 Map-reduce over a corpus

Spawn one subagent per document → each emits a structured summary → reduce step
synthesizes. Pattern for "summarize this 200-doc folder" tasks. The reducer is the
hub; subagents are pure functions.

### Coordination tradeoff table

| Pattern        | Latency | Cost | Best for                              | Pitfall                              |
|----------------|---------|------|---------------------------------------|--------------------------------------|
| Parallel fan-out | Low     | High | Independent research                  | Result-merge prompt blowup           |
| Sequential     | High    | Med  | Dependent reasoning                   | Error compounds across stages        |
| Critic pair    | Med     | High | Quality-critical drafting             | Infinite-loop if critic too strict   |
| Map-reduce     | Low     | High | Large-corpus summarization            | Loses cross-doc relationships        |

---

## 1.5 The SPIDER Reliability Pattern

SPIDER is Anthropic's recommended structure for **per-step reliability** inside an
agentic loop. Every CCA-F exam form has at least one SPIDER question.

| Letter | Stage          | What happens                                              |
|--------|----------------|-----------------------------------------------------------|
| **S**  | Specify        | Restate the task in unambiguous terms before acting       |
| **P**  | Plan           | Sketch the steps and the expected end state               |
| **I**  | Implement      | Execute one step (tool call or generation)                |
| **D**  | Defend         | Validate the output against the spec (schema, invariants) |
| **E**  | Evaluate       | Did the step move us toward the goal? Score it            |
| **R**  | Refine         | If the score is low, revise the plan; else, advance       |

### Why SPIDER beats a naive ReAct loop

- ReAct ("Thought → Action → Observation") has no defense or evaluation step. The
  model can confidently march off a cliff.
- SPIDER bakes verification into every iteration, catching tool errors and bad
  outputs *before* they corrupt downstream context.
- It maps cleanly to a logging schema — each letter is a span you can audit.

### SPIDER as a Python skeleton

```python
def spider_step(state, goal, tools):
    spec     = specify(state, goal)            # S — clarified subgoal
    plan_    = plan(spec)                      # P — concrete actions
    output   = implement(plan_, tools)         # I — execute
    issues   = defend(output, spec.schema)     # D — schema/invariant check
    score    = evaluate(output, goal)          # E — fitness 0..1
    if issues or score < 0.6:
        return refine(state, plan_, issues)    # R — revise & retry
    return advance(state, output)
```

### Exam framings of SPIDER

- "Your agent intermittently produces malformed JSON downstream. Which SPIDER stage
  should you strengthen?" → **Defend** (schema validation).
- "Your agent picks plausible but wrong tools. Which stage failed?" → **Specify**
  (the subgoal was ambiguous) or **Plan** (action selection).
- "Cost is fine but quality drifts over long sessions." → **Evaluate** + **Refine**
  (no fitness signal, no correction).

---

## 1.6 Autonomous System Design Tradeoffs

This is the "judgment under uncertainty" part of the domain. Memorize these axes —
the exam phrases them as scenarios.

### 1.6.1 Autonomy spectrum

```
  Less autonomous ──────────────────────────────────► More autonomous
  Workflow      Tool-using      Planner-first       Fully agentic
  (scripted)    chatbot         agent               loop with subagents
```

Each step right adds capability and risk. Your job in the exam is to pick the
**leftmost point that satisfies the requirements** — over-autonomy is the most
common wrong answer.

### 1.6.2 The four constraint axes

| Axis            | "Loose" implies                          | "Tight" implies                       |
|-----------------|------------------------------------------|---------------------------------------|
| Latency         | Multi-agent, deep loops OK               | Single agent, shallow loops, cache    |
| Cost            | Opus everywhere                          | Haiku planner, Sonnet workers, batch  |
| Determinism     | Agentic loop                             | Workflow with model in narrow steps   |
| Auditability    | Free-form output                         | Structured output + spans + replay    |

### 1.6.3 Failure-mode catalog (exam favorite)

| Symptom                            | Likely cause                          | Fix                                   |
|------------------------------------|---------------------------------------|---------------------------------------|
| Loop never terminates              | Tool returns ambiguous "success"      | Tighten tool result schema            |
| Costs spiral                       | No max-iter cap; recursive subagents  | Cap iterations; flatten hierarchy     |
| Subagents repeat each other's work | Orchestrator gives overlapping briefs | Tighten task decomposition            |
| Output occasionally malformed      | No SPIDER Defend; no JSON mode        | Add schema validation + retry         |
| Quality drops in long sessions     | Context window saturation             | Prompt caching + summary compaction   |
| Tool calls succeed but wrong ones  | Underspecified tool descriptions      | Improve tool name/description/schema  |
| Tools clash on shared state        | No isolation                          | Per-subagent sandboxes                |

### 1.6.4 The "blast radius" rule

Before granting an agent autonomy, ask: **what is the worst thing it can do in one
step?** If the answer is "delete production data" or "wire money", you need a
human-in-the-loop confirmation, not just better prompts. The exam loves this scenario.

---

## 1.7 Architecture Decision Frameworks

### Framework A — Single-agent vs Multi-agent

```
START
  │
  ├─ Can the task be expressed as one prompt + a few tools?
  │     YES → SINGLE AGENT. Stop here.
  │     NO  → continue
  │
  ├─ Are the subtasks INDEPENDENT (no shared mutable state)?
  │     YES → multi-agent w/ parallel fan-out
  │     NO  → continue
  │
  ├─ Is the workflow sequence KNOWN?
  │     YES → workflow with single-agent steps
  │     NO  → multi-agent w/ planner-first or dynamic decomposition
  │
  └─ Default: hub-and-spoke with Opus orchestrator + Sonnet workers
```

### Framework B — Where to spend the bigger model

| Role              | Default tier      | Reason                                    |
|-------------------|-------------------|-------------------------------------------|
| Orchestrator/plan | Opus 4.7          | Reasoning quality dominates cost          |
| Subagent worker   | Sonnet 4.6        | Throughput + capability balance           |
| Critic/judge      | Sonnet 4.6        | Independent evaluator, capable but cheap  |
| Planner-only      | Haiku 4.5         | Plan generation is cheap; speed matters   |
| Classifier/router | Haiku 4.5         | Latency-critical, low complexity          |

### Framework C — When to add a tool vs a subagent

| Add a **tool** when…                                  | Add a **subagent** when…                            |
|-------------------------------------------------------|-----------------------------------------------------|
| The capability is deterministic (DB query, API)       | The capability requires reasoning over many turns   |
| Output fits in <2k tokens                             | Output requires its own context window              |
| Same agent should handle the result                   | A specialist mindset/system prompt helps            |
| You want auditable side effects                       | You want to isolate a context blowup                |

> **Exam gotcha:** "Add a subagent that calls the database" is almost always wrong —
> a subagent is overkill for a deterministic lookup. The right answer is a tool.

---

## 1.8 Practice MCQs (Domain 1)

> Real-exam style. Each is 4-option, single-correct, scenario-anchored. Answers and
> rationale at the bottom of the section.

---

**Q1.** A fintech team is building a Claude-driven workflow that **executes trades
on behalf of users**. Average daily volume is 50,000 trades, each requiring lookup
of risk limits, position checks, and an order placement. Audit and reproducibility
are mandated by their regulator. Which architecture best fits?

A. Hub-and-spoke with an Opus orchestrator deciding each trade's path dynamically.
B. A deterministic workflow that calls Claude only for narrow free-form steps (e.g.
   summarizing rationale), with all decision logic in code.
C. A fully agentic loop with `max_tokens=8192` and a "place_order" tool.
D. Map-reduce, with one subagent per trade.

---

**Q2.** Your research agent works well for single-topic queries but **struggles
when users ask broad questions like "summarize the state of nuclear fusion R&D
across 5 dimensions"**. Costs are acceptable; latency is not the bottleneck.
Which change has the highest expected ROI?

A. Switch the agent to Haiku to allow longer loops within the cost budget.
B. Add a planner-first decomposition step that fans out to per-dimension subagents,
   then synthesizes.
C. Increase `max_tokens` to 16,384 so the single agent can write a longer answer.
D. Add a vector-DB retrieval tool so the agent grounds answers in cached papers.

---

**Q3.** A team's agentic loop **occasionally never terminates** in production. On
inspection, the model keeps re-invoking a `search_database` tool that always
returns `{"status": "ok"}` regardless of result count. Which SPIDER stage is the
weakest link?

A. Specify
B. Plan
C. Defend
D. Evaluate

---

**Q4.** You're designing a Claude-based code-review agent that must read 12 files,
critique each, and return a unified report. The files are independent. Latency
budget is 30 seconds. Which orchestration is best?

A. Single agent that reads all 12 files into context and critiques sequentially.
B. Sequential pipeline: agent reads file 1, critiques, reads file 2, critiques, ...
C. Hub-and-spoke with parallel fan-out: 12 subagents, one per file, then a
   synthesis step.
D. Peer-to-peer: 12 agents that gossip critiques among themselves.

---

**Q5.** Your orchestrator's context window is **filling up after 20+ subagent
calls**, and quality is dropping. The orchestrator currently appends each
subagent's full transcript. What is the BEST fix?

A. Increase the orchestrator's `max_tokens`.
B. Switch the orchestrator to a model with a larger context window.
C. Have each subagent return a structured summary; orchestrator keeps only the
   summary, not the transcript.
D. Run the orchestrator with prompt caching enabled.

---

**Q6.** A teammate proposes adding a "plan_trip" subagent that calls a single
`get_flights` API and returns the results. Travel-app traffic is 100 RPS. What is
the strongest argument **against** this design?

A. Subagents should never call external APIs.
B. A subagent for a deterministic API call is overkill — a tool achieves the same
   capability with lower latency, lower cost, and simpler observability.
C. The orchestrator must call the API directly to avoid context leakage.
D. Subagents are not allowed to return structured data.

---

**Q7.** You have a "summarize this PR" agent. Sometimes it returns a summary;
sometimes it returns malformed JSON; sometimes it returns nothing. The error rate
is 4%. Which intervention addresses the **root cause** most directly?

A. Increase `temperature` to encourage diverse outputs.
B. Add a Defend stage that validates the JSON schema and triggers a Refine retry
   on failure.
C. Switch to Opus 4.7 and accept the cost increase.
D. Wrap the call in a try/except and return a default summary.

---

**Q8.** A startup's "autonomous data analyst" agent has a `delete_table` tool. The
tool's blast radius is high. The agent operates without human approval. Which
design choice is the most important to revisit?

A. The model tier — should be Opus, not Sonnet.
B. The system prompt's tone.
C. The autonomy level — destructive tools require human-in-the-loop confirmation
   regardless of prompt quality.
D. The temperature.

---

**Q9.** Your hub-and-spoke research system spawns **5 subagents that overlap
heavily** ("history of fusion", "fusion timeline", "fusion milestones"...). What
SPIDER stage at the orchestrator level is failing?

A. Specify (the subgoals are not disjoint)
B. Defend
C. Evaluate
D. Refine

---

**Q10.** A team ships a customer-support agent. They are **considering
peer-to-peer** coordination among three agents: an "intent classifier", a
"knowledge base agent", and a "tone agent". Why is hub-and-spoke better for this
scenario?

A. Peer-to-peer is incompatible with the Anthropic SDK.
B. Hub-and-spoke is O(N) coordination versus peer-to-peer's O(N²); for a small
   pipeline with a clear sequence, the orchestrator gives determinism, single
   trace, and bounded blast radius.
C. Peer-to-peer requires a vector database.
D. Peer-to-peer requires Opus on every node.

---

### Answers & Rationale

| Q  | Ans | Why                                                                                      |
|----|-----|------------------------------------------------------------------------------------------|
| 1  | B   | Regulated, deterministic workflow; agent is overkill and breaks audit. **D1.6**          |
| 2  | B   | Independent dimensions ⇒ parallel fan-out subagents w/ planner. Classic hub-and-spoke.    |
| 3  | C   | Tool's "ok" hides failure ⇒ Defend (schema/invariant check) is missing.                  |
| 4  | C   | 12 independent files + tight latency ⇒ parallel fan-out. A is too much context for one.  |
| 5  | C   | Context isolation is the *whole point* of hub-and-spoke. Summaries up, traces down.      |
| 6  | B   | Subagent for a deterministic API = anti-pattern. Use a tool.                              |
| 7  | B   | Schema-validate-and-retry is the SPIDER Defend+Refine pattern; root-cause fix.           |
| 8  | C   | Blast radius rule: destructive tools require HITL, not better prompts.                   |
| 9  | A   | The orchestrator failed to *specify* disjoint subgoals; it's a decomposition bug.        |
| 10 | B   | Coordination complexity argument; the structural answer.                                  |

---

## 1.9 Mini-Lab — Build a Production Research Orchestrator

**Goal:** A CLI tool `research.py "<topic>"` that uses hub-and-spoke + SPIDER to
produce a structured research report.

**Deliverables:**
1. Orchestrator (Opus) with planner-first decomposition.
2. 3–5 subagents (Sonnet) running in parallel with a web-search tool.
3. SPIDER Defend stage validating each subagent's JSON output.
4. SPIDER Evaluate stage scoring each subagent; failures are re-tried once.
5. Final synthesis with citations.

**Skeleton (fill in TODOs):**

```python
"""
research.py — production research orchestrator.

Usage: python research.py "state of nuclear fusion R&D"
"""
import sys, json, concurrent.futures as cf
from anthropic import Anthropic
client = Anthropic()

# ---- 1. Schemas (the Defend stage validates against these) ---------------
SUBAGENT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "subtopic": {"type": "string"},
        "bullets": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 7},
        "sources": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
    "required": ["subtopic", "bullets", "sources"],
}

# ---- 2. Tools (web_search is Anthropic's built-in server tool) -----------
TOOLS = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]

# ---- 3. Subagent ---------------------------------------------------------
SUB_SYSTEM = """You are a research subagent. Investigate the assigned subtopic
using web_search. Return ONLY a JSON object matching the schema:
{"subtopic": str, "bullets": [3-7 strings], "sources": [URLs]}."""

def run_subagent(subtopic: str) -> dict:
    messages = [{"role": "user", "content": f"Subtopic: {subtopic}"}]
    for _ in range(8):
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=2048,
            system=SUB_SYSTEM, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "end_turn":
            text = "".join(b.text for b in resp.content if b.type == "text")
            try:
                data = json.loads(text)
                # SPIDER Defend
                _validate(data, SUBAGENT_OUTPUT_SCHEMA)
                return data
            except Exception as e:
                # SPIDER Refine — retry once with the error surfaced
                messages.append({"role": "user", "content": f"Validation failed: {e}. Return valid JSON."})
                continue
        # TODO: handle tool_use blocks (web_search is server-side, so SDK auto-runs)
    return {"subtopic": subtopic, "bullets": [], "sources": [], "error": "timeout"}

def _validate(data, schema):
    # Minimal validator. In prod, use jsonschema.validate.
    for k in schema["required"]:
        if k not in data:
            raise ValueError(f"missing {k}")
    if not (3 <= len(data["bullets"]) <= 7):
        raise ValueError("bullets out of range")

# ---- 4. Orchestrator (planner + synthesis) -------------------------------
ORCH_PLAN = """Decompose the goal into 4 disjoint subtopics. JSON only:
{"subtopics": [str, str, str, str]}."""

ORCH_SYNTH = """Synthesize the subagent reports into a coherent briefing.
Cite sources inline as [1], [2], etc."""

def orchestrate(goal: str) -> str:
    # Phase 1: plan
    plan = json.loads(client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=512,
        system=ORCH_PLAN,
        messages=[{"role": "user", "content": goal}],
    ).content[0].text)

    # Phase 2: parallel subagents
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run_subagent, plan["subtopics"]))

    # SPIDER Evaluate — drop empties, retry once if needed (omitted for brevity)
    valid = [r for r in results if r.get("bullets")]

    # Phase 3: synthesize
    synth_input = json.dumps(valid, indent=2)
    final = client.messages.create(
        model="claude-opus-4-7", max_tokens=4096,
        system=ORCH_SYNTH,
        messages=[{"role": "user", "content": f"Goal: {goal}\nReports:\n{synth_input}"}],
    )
    return "".join(b.text for b in final.content if b.type == "text")

if __name__ == "__main__":
    print(orchestrate(sys.argv[1]))
```

**Stretch goals:**
- Replace the validator with `jsonschema.Draft202012Validator`.
- Add per-subagent token accounting and total-cost reporting.
- Persist subagent outputs to disk so orchestrator can resume on crash.
- Add a critic subagent that scores the final synthesis 0–10 and triggers one revision.

---

## 1.10 Domain 1 Cheatsheet (flashcard-ready)

```
══════════════════════════════════════════════════════════════════════════
DOMAIN 1 — AGENTIC ARCHITECTURE & ORCHESTRATION  (27%)
══════════════════════════════════════════════════════════════════════════

DEFINITIONS
  Agent       = LLM + tools + LOOP + termination logic
  Workflow    = deterministic sequence; model is a step, not the driver
  Orchestrator= the hub agent that plans & dispatches
  Subagent    = isolated-context worker; reports only summaries upward

THE CANONICAL LOOP
  while stop_reason == "tool_use":
      1. Append assistant turn (with tool_use blocks)
      2. Execute every tool_use block
      3. Append SINGLE user turn with all tool_result blocks
         - tool_use_id MUST match
         - errors → is_error: true, NEVER raise
      4. Re-call messages.create

STOP REASONS
  end_turn      → model decided it's done            (TERMINATE)
  tool_use      → model wants to call tools         (CONTINUE)
  max_tokens    → ran out of output budget          (handle / abort)
  stop_sequence → hit a configured stop string      (TERMINATE)
  refusal       → model refused the request         (TERMINATE)

DECOMPOSITION MODES
  Static    → engineer-decided                  $   predictable
  Planner   → LLM plans once, then executes     $$  bounded
  Dynamic   → LLM decides each step in loop     $$$ open-ended

HUB-AND-SPOKE (the default)
  + O(N) coordination, single trace, bounded blast radius
  + context isolation per subagent
  - planner becomes the bottleneck if too smart
  Anti-pattern: subagent for a deterministic API call → use a tool

MODEL TIERING DEFAULT
  Orchestrator/critique → Opus 4.7
  Worker subagents      → Sonnet 4.6
  Plan/classify only    → Haiku 4.5

SPIDER (per-step reliability inside a loop)
  S pecify → restate task unambiguously
  P lan    → enumerate steps + expected end state
  I mplement → execute one step
  D efend  → schema/invariant validation
  E valuate → score progress toward goal
  R efine  → revise plan if low score; else advance

  Common exam mappings:
    Malformed output  → Defend
    Wrong tool picked → Specify or Plan
    Quality drifts    → Evaluate + Refine
    Drives off cliff  → no Defend (ReAct only)

COORDINATION SUB-PATTERNS
  Parallel fan-out  → independent work, sum-cost, max-latency=slowest
  Sequential        → dependent reasoning, error compounds
  Critic pair       → independent evaluator (NOT self-critique)
  Map-reduce        → per-doc summarize → synthesize

AUTONOMY DIAL (pick LEFTMOST that satisfies requirements)
  Workflow → tool-using bot → planner-first → fully agentic

BLAST-RADIUS RULE
  If "worst step" can hurt prod / money / data → human-in-the-loop required
  Better prompts ≠ a substitute for HITL on destructive tools

FAILURE → FIX QUICK TABLE
  loop never terminates       → tighten tool result schema
  cost spirals                → cap iters + flatten subagent depth
  subagents repeat work       → fix decomposition (Specify)
  malformed JSON              → schema-validate + retry (Defend+Refine)
  long-session quality drop   → caching + summary compaction
  tool succeeds w/ wrong tool → improve tool name/desc/schema
  shared-state contention     → per-subagent sandboxes

ANTI-PATTERNS (instant-wrong on the exam)
  ✗ Peer-to-peer when hub-and-spoke would do
  ✗ Subagent for a single deterministic call
  ✗ Self-critique instead of separate critic agent
  ✗ Letting subagent transcripts bleed into orchestrator context
  ✗ Inverted model tiering (Haiku orchestrating Opus)
  ✗ Increasing max_tokens to "fix" reliability problems
  ✗ Removing termination cap to "let it finish"
  ✗ Destructive tools w/ no HITL because "the prompt says be careful"

ARCHITECTURE QUICK CHOOSER
  one prompt + few tools         → SINGLE AGENT
  independent subtasks           → PARALLEL FAN-OUT
  dependent + known sequence     → WORKFLOW with single-agent steps
  dependent + unknown sequence   → DYNAMIC AGENTIC LOOP
  multi-domain / specialists     → HUB-AND-SPOKE w/ subagents
  quality-critical drafting      → GENERATOR + CRITIC PAIR
══════════════════════════════════════════════════════════════════════════
```

---

### Where Domain 1 connects to other domains

- **Tool design (D2):** subagent-vs-tool decisions, tool result schemas (Defend).
- **Claude Code (D3):** Claude Code IS a hub-and-spoke agent — its `Agent` tool
  spawns isolated-context subagents; CLAUDE.md is its system prompt.
- **Prompt engineering (D4):** SPIDER Specify/Plan are prompt-engineering disciplines.
- **Context management (D5):** the reason summaries flow up but transcripts don't is
  a context-budget decision.

> Next up — **Domain 2: Tool Design & MCP Integration (18%)**. Ask when you're ready.
