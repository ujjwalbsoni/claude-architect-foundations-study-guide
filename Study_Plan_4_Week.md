# CCA-F 4-Week Study Plan

> A 28-day plan weighted by exam domain percentages, leading up to a proctored
> exam window of your choosing. Designed for ~1.5–2 hours/day. If you can do
> only one hour, drop the "stretch" item; if you have three, do the optional
> deep dive.
>
> Day-of-week labels assume you start on a Monday. Shift if you don't.

## Domain weights (your time allocation matches these)

| Domain                                     | Exam % | Days budgeted |
|--------------------------------------------|-------:|--------------:|
| D1 Agentic Architecture & Orchestration    |   27%  |       7       |
| D3 Claude Code Config & Workflows          |   20%  |       5       |
| D4 Prompt Engineering & Structured Output  |   20%  |       5       |
| D2 Tool Design & MCP Integration           |   18%  |       5       |
| D5 Context Management & Reliability        |   15%  |       4       |
| Review / mocks / weak-spot drills          |    —   |       2       |
| **Total**                                  | **100%** |   **28**    |

## Setup (do this BEFORE Day 1)

- [ ] Install Python 3.11+, the Anthropic SDK: `pip install anthropic jsonschema`
- [ ] Install the official MCP SDK: `pip install mcp`
- [ ] Install Claude Code: `npm install -g @anthropic-ai/claude-code`
- [ ] Set `ANTHROPIC_API_KEY` in your environment
- [ ] Create a scratch repo `ccaf-labs/` with subfolders for each domain's labs
- [ ] Skim the Anthropic docs landing page once — just the table of contents

---

## WEEK 1 — Agentic Architecture (D1, 27%)

> Goal: by Sunday, you can mentally trace an agentic loop, justify multi-agent
> vs single-agent in one sentence, and identify the SPIDER stage that fixes
> any given symptom.

### Day 1 — The agentic loop, end-to-end
- Read **D1 §1.0–§1.1** (mental model + canonical loop).
- Type out the canonical loop from D1 §1.1 by hand into `agentic_loop.py`.
  Run it. Force a `tool_use` and observe `stop_reason` transitions.
- Inject a tool that **raises an exception**; observe what happens. Then
  switch to `is_error: true` data return. Note the difference in agent
  behavior.

### Day 2 — Task decomposition and model tiering
- Read **D1 §1.2–§1.3** (decomposition + hub-and-spoke).
- Write a planner-first decomposer that uses Haiku for planning, Sonnet for
  execution. Observe the cost difference vs Opus-everywhere.
- Make a list: 5 tasks where you'd choose static decomposition, 5 where
  planner-first, 5 where dynamic. Justify each in one sentence.

### Day 3 — Hub-and-spoke implementation
- Read **D1 §1.3** in detail; type out the orchestrator code.
- Run the parallel fan-out version with 4 subtopics. Then run a serialized
  version. Compare wall-clock and token counts.
- Mini-exercise: introduce a deliberately *overlapping* set of subtopics
  (e.g. "fusion timeline" + "fusion milestones"). Watch quality drop. Fix
  the orchestrator's planner prompt to enforce *disjoint* subtopics.

### Day 4 — Subagent coordination patterns
- Read **D1 §1.4** (parallel / sequential / critic / map-reduce).
- Build a **critic pair**: a generator subagent and a critic subagent with
  *different system prompts*. Loop until critic approves or N rounds.
- Compare to a **self-critique** version (generator critiques itself).
  Note the correlation in errors when self-critiquing.

### Day 5 — SPIDER reliability
- Read **D1 §1.5** carefully; the exam tests this aggressively.
- For each SPIDER letter, write a 1-paragraph example of a failure that
  pinpoints that stage.
- Take your hub-and-spoke from Day 3 and add **Defend** (jsonschema validate
  on subagent output) + **Refine** (one retry with surfaced errors).

### Day 6 — Mini-Lab: production research orchestrator
- Implement the **D1 §1.9 mini-lab** end-to-end.
- Acceptance: planner-first decomposition, 4 parallel Sonnet subagents,
  Defend stage on each, Opus synthesis with citations.
- Stretch: add a critic subagent that scores the synthesis 0–10 and triggers
  one revision if < 7.

### Day 7 — D1 review & practice MCQs
- Take **all 10 D1 practice MCQs** (D1 §1.8) timed (90 sec each). No notes.
- Score yourself. For each miss, re-read the relevant subsection.
- Re-read the **D1 cheatsheet** and write its key tables from memory on
  paper. The act of writing locks it in.

---

## WEEK 2 — Claude Code & MCP (D3 20% + D2 18%)

### Day 8 — CLAUDE.md hierarchy
- Read **D3 §3.0–§3.1**.
- In a scratch repo, create all four CLAUDE.md locations (user, project,
  local, sub-tree). Put deliberately conflicting instructions in two of them.
  Run a Claude Code session and observe how the model reconciles.
- Practice: write a 30-line user `CLAUDE.md`, a 200-line project one, a
  module-specific sub-tree one. Justify what's in each.

### Day 9 — Settings, permissions, and modes
- Read **D3 §3.2–§3.3**.
- In your scratch repo, write a `settings.json` with allow/deny/ask, plus
  patterns (`Bash(cmd:*)`, `Edit(glob)`, `WebFetch(domain:...)`).
- Test: try a denied command and watch the rejection. Try `--permission-mode
  plan` and observe what's blocked.

### Day 10 — Slash commands, subagents, and hooks
- Read **D3 §3.4–§3.6**.
- Write a `/release-notes` slash command, a `reviewer` subagent, and a
  `PostToolUse` format hook. Trigger each.
- Quiz yourself: when do you use a slash command vs subagent vs hook? Write
  one-sentence answers from memory before checking the cheatsheet.

### Day 11 — SDK + CI/CD recipe
- Read **D3 §3.7**.
- Write a Python script that calls `claude -p` with `--output-format
  stream-json` and parses events. Pin the model. Use `--max-turns`.
- Mini-Lab: implement the **D3 §3.11 `payments-service` setup** (settings,
  hooks, commands, agents, GH Action). You don't need a real PR; verify the
  files compose.

### Day 12 — Tool design fundamentals (D2)
- Read **D2 §2.0–§2.2**.
- Write three tools that are deliberately bad (mega-tool, free-form `query`,
  `manage_user(action)`). Then refactor each into well-bounded tools.
- For each tool, force yourself to write the description with **"Do NOT use
  this for X"** disambiguating against neighbors.

### Day 13 — MCP transports & implementations
- Read **D2 §2.3–§2.4**.
- Implement the **stdio MCP server** from D2 §2.4. Wire it into Claude Code
  via `.mcp.json`. List its tools, call one.
- Implement the **SSE MCP server** with bearer auth from D2 §2.4. Hit it
  with a curl `Authorization: Bearer …` to confirm 401 without, 200 with.

### Day 14 — D2 deep + practice MCQs
- Read **D2 §2.5–§2.10** (auth, resources, lifecycle, boundary decisions,
  full billing-server example).
- Take **all 10 D2 MCQs** + **all 10 D3 MCQs** (20 total) timed. Score.
- Re-read the cheatsheets for both domains. Write their anti-pattern lists
  from memory.

---

## WEEK 3 — Prompt Engineering & MCP Mini-Lab (D4 20% + D2 close-out)

### Day 15 — PRECISE framework
- Read **D4 §4.0–§4.1**.
- Take a real prompt you've written (or pull one from a project) and rewrite
  it in PRECISE form. Compare line-by-line.
- Identify the most common inversion you make personally (persona at the
  bottom? schema in prose?).

### Day 16 — Roles + structured output
- Read **D4 §4.2–§4.3**.
- Implement Levels 1, 2, and 3 of structured output (D4 §4.3) for a sentiment
  classifier. Measure malformed-output rate on a synthetic dataset of 200
  examples for each level.
- Internalize the **pre-fill trick** and the gotcha that pre-fill output
  isn't echoed.

### Day 17 — Few-shot + CoT
- Read **D4 §4.4–§4.5**.
- Build a 12-class intent classifier with: (a) static 12-example few-shot,
  and (b) dynamic top-3 retrieved few-shot. Compare on a held-out set.
- For one task that needs reasoning (e.g. expense categorization with policy),
  add structured CoT (`<thinking>` + `<answer>`) and parse only the answer.

### Day 18 — Validation retry loops
- Read **D4 §4.6–§4.7**.
- Implement the full **validate-and-retry** loop from D4 §4.7. Stress-test it
  by feeding adversarial inputs that force schema violations. Observe the
  refine messages and retry behavior.
- Add API-retry on 429/5xx with exponential backoff.

### Day 19 — Evaluation + Mini-Lab
- Read **D4 §4.9** (evaluation).
- Build the **D4 §4.11 hardened classifier mini-lab**: PRECISE prompt + cached
  system + forced tool-use + jsonschema retry + eval script.
- Run the eval script on a labeled `tickets.jsonl`. Inspect the `failures.json`
  bucket and add one of those failures as a new few-shot example.

### Day 20 — D4 practice MCQs + D2 MCP mini-lab
- Take **all 10 D4 MCQs** timed. Score.
- Read **D2 §2.12 mini-lab** (Notes MCP server). Implement at least: tools,
  resource, bearer auth, idempotency on `create_note`. Stretch: pagination
  on `search_notes`.

### Day 21 — Cumulative review
- Re-read **D1, D2, D3, D4 cheatsheets** in order.
- Quiz yourself: pick 5 random anti-patterns across the four domains; for
  each, state the right architecture in one sentence.
- Write down 3 questions you still feel shaky on; mark them for the Week-4
  review.

---

## WEEK 4 — Context Management + Final Review (D5 15% + mocks)

### Day 22 — Token budget + caching
- Read **D5 §5.0–§5.2**.
- Take a real prompt with a long system message. Add `cache_control` and
  measure `cache_read_input_tokens` over 10 calls. Confirm the read price.
- Stress-test: insert `datetime.now()` into the cached prefix; watch the
  cache hit rate go to zero. Move it out; recover.

### Day 23 — CALM + multi-turn design
- Read **D5 §5.3–§5.4**.
- Implement the **multi-turn production pattern** from D5 §5.4. Stress-test
  with 50+ turns and an artificially huge tool result; observe how
  `_cap` and `_compact` behave.
- Quiz yourself on CALM: one sentence per letter, applied to your codebase.

### Day 24 — RAG patterns
- Read **D5 §5.5**.
- Build a vanilla RAG over a small doc corpus (say, 30 markdown files).
- Convert it to **tool-driven retrieval** (agent calls `search_kb` itself).
  Compare: which one answers "I don't know" more reliably? Which attributes
  better?
- Add source labels (`[doc:id]`) to every snippet — this is CALM Attribute
  in action.

### Day 25 — Reliability + Mini-Lab
- Read **D5 §5.6**.
- Implement the **D5 §5.9 mini-lab**: cached, compacting, RAG-backed
  assistant with checkpointing.
- Acceptance: persona is cached across sessions, conversation compacts at
  60K tokens, tool results capped at 6KB, session restores from disk.

### Day 26 — Full mock exam #1
- Take **all 50 MCQs across all domains** in one sitting (60–75 min, ~90s
  each, no notes). This simulates ~80% of a real exam.
- Score by domain. Anything below 70% in a domain → that's tomorrow's focus.
- Read the answer keys for every miss and the surrounding subsection.

### Day 27 — Weak-spot drill + cheatsheet review
- Pick the 2 weakest domains from the mock. Re-read their cheatsheets.
- Re-do the practice MCQs for those domains; aim for 100% second pass.
- Speed-pass: read **all 5 cheatsheets** end to end. Time yourself; you
  should finish in 30–40 minutes.
- For the 3 questions you flagged on Day 21, write one-paragraph answers and
  check them against the source domains.

### Day 28 — Final review and rest
- Light review only — don't cram. Re-read each domain's "Anti-patterns
  (instant-wrong)" list once.
- Re-read the **Exam Strategy** section below.
- Sleep early. Hydrate. Confirm proctoring setup the day before, not the
  morning of.

---

## EXAM-DAY STRATEGY

### Time management
- 60 questions / 120 minutes = 2 minutes per question on average.
- Aim for **90 seconds** per question on the first pass; flag the others.
- Reserve the **last 15 minutes** for flagged questions.

### Reading the question
- **Anchor on the constraints.** Every scenario lists 2–4 constraints
  (latency, cost, audit, multi-user). Underline them mentally.
- **Identify the role.** Are you the architect, the IC, the SRE? Distractors
  often fit the wrong role.
- **Spot the distractor pattern.** The wrong answer often:
  - Adds a feature that doesn't address the root cause (CoT for classifiers,
    bigger context window for compaction problems).
  - Suggests a model swap when the issue is design.
  - Solves the symptom, not the cause (try/except instead of validation).
  - Inverts a tradeoff (peer-to-peer when hub-and-spoke fits).

### Per-domain mental shortcuts

- **D1**: when in doubt, hub-and-spoke + Sonnet workers + Opus orchestrator.
  HITL on destructive tools. SPIDER **Defend** is the most-asked stage.
- **D2**: stdio for local, SSE for remote. Resources for read-only. Tool
  boundaries: one verb per tool. Auth at transport, never in tool inputs.
- **D3**: hooks for "always do X", not CLAUDE.md. Permission `deny` wins.
  CLAUDE.md files **compose**, don't override.
- **D4**: forced tool-use for structured output. Validate-and-retry with
  *concrete* error feedback. Eval set, not spot-checks.
- **D5**: cache the stable prefix; cap tool results; compact long sessions.
  "Bigger context window" is rarely the answer.

### When two answers look right

Pick the one that:
1. Addresses the **root cause**, not the symptom.
2. Matches the **leftmost autonomy** that satisfies the requirement.
3. Uses the **lowest-blast-radius** mechanism that meets the goal.
4. Is the **simplest** architecture that still works.

### Last-minute red flags (any of these in an answer = probably wrong)

- "Use bypassPermissions in production"
- "Inline the secret in CLAUDE.md / settings.json"
- "Switch to a model with a bigger context window" (when the bug is design)
- "Increase max_tokens" (as a fix for quality)
- "Self-critique" (when a separate critic is implied)
- "Use a single mega-tool with an action enum"
- "Disable hooks to remove non-determinism"
- "Spot-check 5 outputs and ship"

---

## CHECKLIST — am I ready?

Mark each only if you can do it without notes.

**D1 (Agentic — 27%)**
- [ ] Sketch the canonical loop with stop_reason transitions
- [ ] State 3 reasons hub-and-spoke beats peer-to-peer
- [ ] Map any failure symptom to a SPIDER stage
- [ ] Justify model tiering (Opus / Sonnet / Haiku) by role

**D2 (MCP — 18%)**
- [ ] Pick stdio vs SSE for any scenario, with reasoning
- [ ] Write a tool description that includes "Do NOT use for X"
- [ ] Identify when to use a resource vs a tool
- [ ] Place auth at the right architectural layer

**D3 (Claude Code — 20%)**
- [ ] Place a setting in user / project / local correctly
- [ ] Choose hook vs slash command vs subagent
- [ ] Write a CI/CD recipe with explicit allowlist + max-turns
- [ ] Resolve a CLAUDE.md compose-vs-override question

**D4 (Prompt Eng — 20%)**
- [ ] Apply PRECISE to a new prompt from scratch
- [ ] Write a forced-tool-use call with `tool_choice`
- [ ] Implement validate-and-retry with concrete error feedback
- [ ] Distinguish CoT-helps vs CoT-wastes scenarios

**D5 (Context — 15%)**
- [ ] Place `cache_control` correctly given a stable prefix
- [ ] Choose RAG vs long context vs fine-tuning
- [ ] Apply CALM to a multi-turn design problem
- [ ] Cap tool results without breaking pagination

**Mocks**
- [ ] Score ≥ 80% on the cumulative mock exam
- [ ] No domain below 70%

If all boxes are ticked, you're ready. Schedule the proctored slot. Good luck.
