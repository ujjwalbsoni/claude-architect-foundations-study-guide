# Domain 4: Prompt Engineering & Structured Output (20% of CCA-F)

> ~12 of 60 questions. Tied with Claude Code for second-largest weight. The exam
> tests **engineering discipline applied to prompts** — JSON schemas, retry loops,
> evaluation, role separation. "Just write a clearer prompt" is almost never the
> right answer; the right answer is a *system* (validation, retries, examples,
> caching) around the prompt.

---

## 4.0 Mental Model — A Prompt Is an Interface, Not a Spell

The cleanest mental frame for this domain:

> **A prompt is an interface contract between your system and the model.**
> The same engineering rigor you'd apply to a typed API — schemas, examples,
> versioning, tests, retries — applies to prompts.

Three corollaries the exam will test:

1. **Validate model output like untrusted user input.** Schema-validate, retry
   with the error surfaced, fail loudly when retries exhaust. The Domain 1
   SPIDER "Defend" stage is this corollary in agentic clothing.
2. **Examples beat exhortation.** Two well-chosen few-shot examples outperform
   ten paragraphs of "please do X." If your prompt has more *rules* than
   *demonstrations*, you have an inverted prompt.
3. **System and user roles are not stylistic — they're architectural.**
   System = persistent contract; user = the request. Mixing them ("user role
   contains 'You are a friendly assistant'") is the cardinal sin.

---

## 4.1 The PRECISE Framework

Anthropic's recommended structure for production prompts. Every form of the
exam has at least two PRECISE-tagged questions.

| Letter | Stage           | What goes in this stage                                        |
|--------|-----------------|----------------------------------------------------------------|
| **P**  | **P**ersona / Role | Who Claude is in this interaction (system role)             |
| **R**  | **R**equest      | The single, atomic task being asked                           |
| **E**  | **E**xamples     | 1–N few-shot input/output pairs                               |
| **C**  | **C**ontext      | Domain knowledge, constraints, data Claude needs              |
| **I**  | **I**nstructions | Step-by-step procedure (often as ordered list)                |
| **S**  | **S**chema       | Output format definition (JSON schema, XML tags, etc.)        |
| **E**  | **E**valuation / Edge cases | What "good" looks like; failure modes to handle    |

### PRECISE in practice — annotated example

```python
SYSTEM_PROMPT = """\
# PERSONA
You are a senior fraud analyst at a payments company. You are direct,
evidence-driven, and never speculate without naming the evidence.

# REQUEST
For each transaction in the input, classify it as APPROVE, REVIEW, or DECLINE,
and explain your reasoning in <= 2 sentences.

# CONTEXT
- Our risk tolerance is moderate: we'd rather REVIEW a marginal case than DECLINE.
- A "device_age_days" < 1 is a strong fraud signal.
- Cross-border transactions over $1,000 are high-risk by default.
- Returning customers (>= 5 prior orders) get one tier of leniency.

# INSTRUCTIONS
1. Read the transaction record in <transaction>...</transaction>.
2. Identify the strongest signals (positive and negative).
3. Classify into APPROVE | REVIEW | DECLINE.
4. Output ONLY the JSON object specified in the schema; no preamble, no postscript.

# SCHEMA
Output a JSON object matching:
{
  "decision": "APPROVE" | "REVIEW" | "DECLINE",
  "evidence": [string, ...],          // strongest signals you used
  "reasoning": string                  // <= 2 sentences
}

# EXAMPLES
<transaction>{"amount":12.50,"device_age_days":820,"prior_orders":31}</transaction>
{"decision":"APPROVE","evidence":["mature device","high prior_orders"],"reasoning":"Low-value, returning customer on a long-lived device."}

<transaction>{"amount":2400,"device_age_days":0,"prior_orders":0}</transaction>
{"decision":"DECLINE","evidence":["new device","no order history","high amount"],"reasoning":"All three high-risk signals stack; immediate decline is appropriate."}

# EDGE CASES
- Missing fields: assume worst case (treat as 0 / new).
- Conflicting signals (e.g. high amount + many prior orders): output REVIEW.
- If you cannot classify, output {"decision":"REVIEW","evidence":["insufficient data"],"reasoning":"Insufficient signal."}
"""
```

### Why PRECISE survives where "be careful" doesn't

- **Persona** primes vocabulary and stance — fraud analyst ≠ poet.
- **Examples** are anchored input/output pairs the model can extrapolate from
  more reliably than from rules alone.
- **Schema** removes ambiguity from the *output side* of the interface.
- **Edge cases** preempt 80% of the failure modes you'd otherwise hit at
  evaluation time.

### Common PRECISE inversions (exam distractors)

| Inversion                                              | Why it fails                                       |
|--------------------------------------------------------|----------------------------------------------------|
| Persona buried at the bottom                           | The role primes the rest; needs to come first      |
| Examples placed before context                         | Examples without context look like a pattern game  |
| Schema specified in prose instead of JSON              | Model approximates instead of conforms             |
| Edge cases as a wishlist instead of explicit fallbacks | Model invents its own (often wrong) fallback       |

---

## 4.2 Role Prompting (System vs User vs Assistant)

The exam distinguishes between **role prompting** (using the system role to set
persona + invariants) and ad-hoc style instructions in the user message.

### What goes where

| Role        | Contains                                                               |
|-------------|------------------------------------------------------------------------|
| `system`    | Persona, format/schema contract, invariants, examples, tools-context |
| `user`      | The current request, the raw input data, the immediate question      |
| `assistant` | Past turns; few-shot canned outputs; pre-fills (see §4.4)            |

### The pre-fill trick (high-ROI, exam-favorite)

You can seed the assistant's response by adding a partial assistant turn at
the end of `messages`. Claude continues *from* that text — useful for forcing
JSON output and stripping preamble.

```python
resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=1024,
    system=SYSTEM_PROMPT,
    messages=[
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": "{"},   # <-- pre-fill
    ],
    stop_sequences=["\n\n"],   # optional: stop after the JSON block
)

# resp.content[0].text now starts WITHOUT the leading "{" — re-add it before parsing.
output = "{" + resp.content[0].text
data = json.loads(output)
```

> **Exam gotcha:** When you pre-fill, the model's output **does not include**
> the pre-fill string. You must concatenate it back before parsing. This trips
> up half of candidates.

### Anti-patterns

- **System role used as a scratchpad.** Putting the user's literal question in
  system is "I have no idea what role means."
- **Persona in the user role.** "You are a friendly support agent. Now: my
  laptop won't turn on." Two failure modes: persona resets on each turn, and
  it competes with the genuine user content.
- **Multiple personas.** "You are a fraud analyst. You are also a translator
  and a poet." Pick one role per agent; if you need three personas, you need
  three subagents (Domain 1).

---

## 4.3 Structured Output — JSON Schema Enforcement

Three levels of rigor, increasing in cost and reliability:

### Level 1 — Prompt-level schema (cheapest, ~95% reliable)

Tell the model the schema in the system prompt and pre-fill `{`:

```python
system = (
    "Return ONLY a JSON object matching:\n"
    '{"sentiment": "positive"|"negative"|"neutral", '
    '"score": number in [0,1], "rationale": string}\n'
    "No preamble. No markdown. No code fences."
)
```

### Level 2 — Tool-use as a typed return (~99% reliable)

Define a tool whose `input_schema` is your output schema. Force the model to
call it via `tool_choice`:

```python
SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "string", "enum": ["positive", "negative", "neutral"]},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale": {"type": "string"},
    },
    "required": ["sentiment", "score", "rationale"],
    "additionalProperties": False,
}

resp = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=512,
    tools=[{"name": "emit_classification",
            "description": "Emit the classification result.",
            "input_schema": SCHEMA}],
    tool_choice={"type": "tool", "name": "emit_classification"},   # forced
    messages=[{"role": "user", "content": user_text}],
)

tool_use = next(b for b in resp.content if b.type == "tool_use")
data = tool_use.input    # already a dict, no parsing
```

The model literally cannot return free-form text when forced; the `input` field
is shape-validated by the API. **This is the exam's preferred answer for
"reliable structured output".**

### Level 3 — Validate-and-retry (the bulletproof loop)

Even with tools, you should validate downstream and retry on schema violations.
This is the SPIDER `Defend → Refine` pattern in prompt-engineering form.

```python
"""
structured.py — bulletproof JSON output with schema-validate-and-retry.

WHY this shape:
  * Tools force the JSON shape but don't enforce semantic invariants
    (e.g. score in [0, 1] inside business rules).
  * On a violation, we surface the actual error to the model and ask
    for a corrected output — this fixes 80% of remaining errors in one round.
  * After MAX_RETRIES, we raise loudly. Silent fallback is the wrong move
    in production: you want to know which inputs broke the prompt.
"""
import json
from anthropic import Anthropic
from jsonschema import Draft202012Validator, ValidationError

client = Anthropic()
MAX_RETRIES = 2

def validated(system: str, user: str, schema: dict, model="claude-sonnet-4-6") -> dict:
    validator = Draft202012Validator(schema)
    messages = [{"role": "user", "content": user}]

    for attempt in range(MAX_RETRIES + 1):
        resp = client.messages.create(
            model=model, max_tokens=1024, system=system,
            tools=[{"name": "emit", "description": "Emit the result.",
                    "input_schema": schema}],
            tool_choice={"type": "tool", "name": "emit"},
            messages=messages,
        )

        # Append assistant turn — required before any further user turn.
        messages.append({"role": "assistant", "content": resp.content})

        try:
            data = next(b.input for b in resp.content if b.type == "tool_use")
        except StopIteration:
            # Force-tool-choice should guarantee a tool_use; if absent, treat as failure.
            messages.append({"role": "user", "content":
                             "You did not call the emit tool. Call it now."})
            continue

        # Defend stage — schema validation
        errors = list(validator.iter_errors(data))
        if not errors:
            return data

        # Refine stage — surface the concrete error and retry
        msg = "\n".join(f"- {e.message} at {list(e.path)}" for e in errors)
        messages.append({"role": "user", "content":
                         f"Validation errors:\n{msg}\nFix and re-emit."})

    raise RuntimeError(f"validated() exceeded {MAX_RETRIES} retries")
```

> **Exam framing:** If the prompt asks "the model occasionally produces a `score`
> > 1," the answer is **add a validate-and-retry loop**, not "increase
> max_tokens" or "switch models."

### Decision: which level for which system?

| Need                                                | Level             |
|-----------------------------------------------------|-------------------|
| Internal one-shot, you'll eyeball outputs           | Level 1           |
| Production pipeline, schema-shaped output           | Level 2           |
| Production pipeline + business invariants           | Level 3 (= 2 + retry) |
| Streaming UI                                        | Level 1 + lenient parse + reconcile-on-finish |

---

## 4.4 Few-Shot Prompting

Few-shot is the highest-leverage prompt-engineering technique. The exam tests
**how many** examples and **how to pick them**.

### Rules

1. **Two beats one. Three beats two. Beyond ~5, returns flatten.** Cost grows
   linearly; quality plateaus. Don't pile on.
2. **Cover the edge cases you care about.** If your task has three classes,
   show one example of each. If you have a known tricky case, include it.
3. **Examples are part of the system prompt** (or the early conversation).
   Putting them after the user's question is a workflow bug — the model has
   already started reasoning.
4. **Format match.** Examples must use *exactly* the output format you want
   the model to emit (including punctuation, casing, whitespace). The model
   pattern-matches more than it reads instructions.

### Few-shot inside system prompt

```python
SYSTEM = """\
You classify customer messages.

# Examples
<message>my package never arrived</message>
{"intent":"shipping_issue","priority":"high"}

<message>do you ship to canada?</message>
{"intent":"shipping_question","priority":"low"}

<message>i was charged twice</message>
{"intent":"billing_issue","priority":"high"}

# Now classify
"""
```

### Few-shot via assistant turns (multi-shot conversation)

```python
messages = [
    {"role": "user", "content": "my package never arrived"},
    {"role": "assistant", "content": '{"intent":"shipping_issue","priority":"high"}'},
    {"role": "user", "content": "do you ship to canada?"},
    {"role": "assistant", "content": '{"intent":"shipping_question","priority":"low"}'},
    {"role": "user", "content": user_input},   # the actual one
]
```

The conversation form is more expensive (tokens × N) but lets you cache the
prefix (Domain 5). **For high-volume pipelines, prefer system-prompt few-shot
+ prompt caching** — same quality, far cheaper at scale.

### Negative examples

You can include "wrong" examples explicitly labeled as wrong, paired with the
correction. Use sparingly; they cost double the tokens of a positive example
and the model can over-anchor on the wrong one if the labeling is unclear.

```
<message>refund pls</message>
WRONG: {"intent":"shipping_issue","priority":"low"}
RIGHT: {"intent":"refund_request","priority":"medium"}
```

### Selection strategy for high-variance domains

If your tasks are heterogeneous (e.g. 30 intent classes), don't include 30
examples — include the 3 closest to the *current* input, retrieved via
embedding similarity. This is "dynamic few-shot" and is a real-exam topic.

```python
# Pseudocode for dynamic few-shot
candidates = embed(user_input).top_k(few_shot_corpus, k=3)
system = render_system_prompt(few_shot_examples=candidates)
```

---

## 4.5 Chain-of-Thought (CoT) Prompting

CoT is asking the model to *reason out loud before committing to an answer*.
Under the hood it gives the model more tokens and serial computation, which
demonstrably improves accuracy on multi-step tasks.

### Three flavors

| Flavor          | Mechanism                                      | When                                |
|-----------------|------------------------------------------------|-------------------------------------|
| **Zero-shot CoT**| "Think step by step before answering."        | Quick wins, low cost                |
| **Few-shot CoT** | Examples that include reasoning *and* answer  | Domains where reasoning style matters |
| **Structured CoT** | Reasoning in `<thinking>` tags, answer in `<answer>` tags | Production: reasoning is private, answer is parsed |
| **Extended thinking** | API-level `thinking: {type:"enabled"}` mode | Deep multi-step problems where you can afford latency/cost |

### Structured CoT (the exam-favored production form)

```python
SYSTEM = """\
You are an expense classifier.

Process:
1. In <thinking> tags, reason about which category fits.
2. After </thinking>, output ONLY the JSON in <answer> tags.

Format:
<thinking>...your reasoning here...</thinking>
<answer>{"category": "...", "confidence": 0.0-1.0}</answer>
"""

# Parsing — extract <answer> only; discard <thinking>
import re
m = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)
data = json.loads(m.group(1))
```

This pattern hits two birds: the model thinks, and your code only parses the
output block. It's also the right shape for **extended thinking**, where
Claude's hidden reasoning is API-managed.

### Extended thinking (Claude-specific)

```python
resp = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=8192,
    thinking={"type": "enabled", "budget_tokens": 4096},
    messages=[{"role": "user", "content": problem}],
)

# resp.content has a thinking block (private) and a text block (the answer).
for b in resp.content:
    if b.type == "thinking":
        # Don't show to end users; useful for logging.
        log.debug(b.thinking)
    elif b.type == "text":
        print(b.text)
```

### When to use CoT vs not

| Use CoT when…                            | Skip CoT when…                                |
|------------------------------------------|-----------------------------------------------|
| Multi-step reasoning (math, causation)   | Pure pattern-matching (sentiment, intent)     |
| Latency budget allows                    | Latency-critical (chat-suggest tier)          |
| You can hide the reasoning from the user | Reasoning would leak business logic           |

> **Exam gotcha:** "Add CoT" is sometimes the wrong fix. If the prompt is a
> simple classification and the model is hitting 99% accuracy, CoT just costs
> more without improvement. Reserve it for problems where intermediate state
> actually changes the answer.

---

## 4.6 System Prompt Design

System prompts are usually 30–500 lines in production. Designing one is its
own skill.

### Structure

```
1. Role / persona               (3-5 lines)
2. Capabilities & boundaries     ("You can: …  You cannot: …")
3. Tools available (if relevant) (1 line per tool with WHEN to use)
4. Output format / schema        (JSON / tags)
5. Tone / style                  (1-2 lines)
6. Examples                      (few-shot)
7. Edge cases & fallbacks        (explicit)
8. Refusal policy                (what to refuse and how to phrase it)
```

### Anti-patterns the exam will flag

| Anti-pattern                                           | What to do instead                            |
|--------------------------------------------------------|-----------------------------------------------|
| 2,000-line "everything" prompt                         | Modularize: persona → tools → schema; cache it |
| Mixing imperatives with conditionals randomly          | Use ordered numbered lists                     |
| Negation-only ("don't say X, don't do Y")              | Pair every negative with a positive ("do Z instead") |
| Restating the same rule 5 times for emphasis           | Once, clearly, near the top                    |
| "Be helpful, harmless, honest" as the only guidance    | Be specific to the task                        |
| User-facing tone instructions in user role             | Move to system                                 |

### The "delimiters help" rule

XML-style tags (`<task>`, `<context>`, `<example>`) are the recommended
delimiters in long prompts. Markdown headers also work. The point is **visual
separation** so the model knows where a section starts and ends.

```
<task>
Classify the customer message.
</task>

<context>
Today is 2026-06-01. The user is a Pro-tier subscriber.
</context>

<message>
{{ user_message }}
</message>
```

### Length vs cost tradeoff

A 500-line system prompt costs ~$0.005/call at Sonnet pricing. With **prompt
caching** (Domain 5), the same prompt costs ~$0.0005/call after the first
hit. **Long, well-cached system prompts are the production pattern**, not an
inefficiency to avoid.

---

## 4.7 Validation Retry Loops — The Production Pattern

The retry loop ties together schema, examples, and refinement.

### The full loop (production-shaped)

```python
"""
retry_loop.py — validate-and-retry with exponential backoff and a circuit breaker.

Production failure modes covered:
  * Transient model errors → retry with backoff
  * Validation errors      → surface to model, ask for fix
  * Persistent failures    → fail loudly with input + last response
  * Cost runaway           → MAX_TOTAL_TOKENS budget per request
"""
import time, json, logging
from anthropic import Anthropic
from anthropic import APIStatusError
from jsonschema import Draft202012Validator

client = Anthropic()
log = logging.getLogger(__name__)

class PromptFailure(Exception): ...

def call_with_retry(*, system, user, schema, model="claude-sonnet-4-6",
                    max_tokens=1024, max_validation_retries=2, max_api_retries=3):
    validator = Draft202012Validator(schema)
    tools = [{"name": "emit", "description": "Emit the result.", "input_schema": schema}]
    messages = [{"role": "user", "content": user}]

    for v_attempt in range(max_validation_retries + 1):
        # API-level retry with backoff
        for a_attempt in range(max_api_retries):
            try:
                resp = client.messages.create(
                    model=model, max_tokens=max_tokens, system=system,
                    tools=tools, tool_choice={"type": "tool", "name": "emit"},
                    messages=messages,
                )
                break
            except APIStatusError as e:
                if e.status_code == 429 and a_attempt < max_api_retries - 1:
                    time.sleep(2 ** a_attempt)        # 1s, 2s, 4s
                    continue
                raise
        else:
            raise PromptFailure("API retries exhausted")

        messages.append({"role": "assistant", "content": resp.content})

        try:
            data = next(b.input for b in resp.content if b.type == "tool_use")
        except StopIteration:
            messages.append({"role": "user", "content":
                             "Call the emit tool with the result."})
            continue

        errors = list(validator.iter_errors(data))
        if not errors:
            return data

        # Refine — concrete, machine-readable error message back to the model
        err_msg = "\n".join(f"- {e.message} at {'/'.join(map(str, e.path)) or '<root>'}"
                            for e in errors)
        log.info("validation_retry attempt=%d errors=%s", v_attempt, err_msg)
        messages.append({"role": "user", "content":
                         f"Validation errors:\n{err_msg}\nReturn corrected result."})

    raise PromptFailure(f"validation retries exhausted after {max_validation_retries+1}")
```

### Where retry loops fit in your stack

```
caller code
   │
   ▼
[call_with_retry]   ← PRECISE prompt + schema + 2 validation retries
   │      │
   │      └─ on failure: PromptFailure → caller logs + alerts
   ▼
Anthropic API       ← per-call API retries on 429 / 5xx
```

> **Exam framing:** "Where should retry logic live for an LLM call?" → **Two
> layers**: API-transport retries on 429/5xx (fast, exponential backoff),
> *plus* application-level validation retries (with the error fed back to the
> model). One alone is insufficient.

---

## 4.8 Output Format Choices

| Format       | Pros                                                | Cons                                          | Use when                                  |
|--------------|-----------------------------------------------------|-----------------------------------------------|-------------------------------------------|
| Free text    | Cheap, easy                                         | Unparseable                                   | Conversation, UX text                     |
| Markdown     | Renders nicely                                      | Loose structure                               | Reports, docs                             |
| JSON in prose | Parseable                                          | Requires extraction; preamble pollution       | Internal tooling, ad hoc                  |
| JSON via tool-use | Strictly typed, no parsing                      | Costs a tool slot                             | **Production structured output**          |
| XML tags     | Easy to extract; robust to whitespace               | Less standard                                 | When mixing reasoning + output            |

### XML extraction utility (handy in retry loops)

```python
import re
def extract_tag(text: str, tag: str) -> str | None:
    m = re.search(fr"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return m.group(1).strip() if m else None
```

### Pre-fill + stop-sequence trick

For Level-1 JSON output, pre-fill `{` and add `}` as a stop sequence so the
model stops cleanly after one object — useful for streaming.

```python
resp = client.messages.create(
    ...,
    messages=[{"role": "user", "content": q},
              {"role": "assistant", "content": "{"}],
    stop_sequences=["}\n"],
)
data = json.loads("{" + resp.content[0].text + "}")
```

---

## 4.9 Evaluation — How You Know the Prompt Is Good

The exam treats prompts as code: they need **tests**.

### A minimal eval loop

```python
"""
eval_prompt.py — run a prompt against a labeled dataset and score it.

Production prompts SHOULD have a stored eval set; new prompt versions
ship only after they beat the prior version on this set.
"""
import json
from anthropic import Anthropic
client = Anthropic()

def score(predicted: dict, expected: dict) -> int:
    return 1 if predicted == expected else 0

def evaluate(prompt_fn, dataset: list[dict]) -> dict:
    correct = 0
    failures = []
    for ex in dataset:
        pred = prompt_fn(ex["input"])
        s = score(pred, ex["expected"])
        correct += s
        if not s:
            failures.append({"input": ex["input"], "got": pred, "want": ex["expected"]})
    return {"accuracy": correct / len(dataset), "failures": failures}
```

### What to build into the loop

- A **golden set** of 30–100 inputs with known correct outputs.
- A **regression check**: new prompt must equal-or-beat the prior on the set.
- A **failure bucket**: collect misses; they become tomorrow's few-shot examples.
- A **drift alert**: re-run weekly with current prompt; alert if accuracy drops
  (could indicate model update or upstream input drift).

> **Exam gotcha:** "How do you know your prompt change is an improvement?"
> The right answer is **measure on a labeled eval set**, not "spot-check
> outputs" or "ask the model if it likes the new prompt."

---

## 4.10 Practice MCQs (Domain 4)

---

**Q1.** Your sentiment classifier returns the right answer 96% of the time, but
**4% of outputs have malformed JSON** (extra preamble, trailing commas). Costs
allow only one change. Which is best?

A. Switch the model from Sonnet to Opus.
B. Add a forced tool-use call (`tool_choice={"type":"tool","name":"emit"}`)
   with the schema as `input_schema`.
C. Add `temperature=0`.
D. Add `"Please return only JSON"` to the user message.

---

**Q2.** A team's prompt asks the model to decide between 12 fraud categories.
Accuracy is 71%. The team adds a 12-example few-shot block to the system prompt;
accuracy moves to 78%. What's the **next** highest-leverage improvement?

A. Add 50 more examples to cover more cases.
B. Switch to a *dynamic few-shot* strategy: at request time, retrieve the 3
   most-similar examples from a labeled corpus.
C. Add CoT instructions.
D. Remove the persona to reduce confusion.

---

**Q3.** A junior teammate puts `"You are a friendly support agent."` at the
start of the user message in every turn. Symptoms: persona drifts mid-conversation,
the model occasionally treats the persona as a *user-supplied* claim and
challenges it. What's the fix?

A. Repeat the persona every 5 user turns.
B. Move persona to the `system` role; it should be set once per session.
C. Increase temperature so persona varies less.
D. Use few-shot examples with the persona repeated.

---

**Q4.** Your validation-retry loop currently retries with `"Try again."`.
Failure rates are still high after one retry. The most direct improvement is:

A. Increase max_retries to 10.
B. On retry, surface the **specific** validation errors (path + message) to
   the model and ask for a corrected output.
C. Switch to JSON-in-prose format.
D. Add a `temperature=1.0` retry to "shake things up."

---

**Q5.** For a structured-output pipeline that must produce a JSON object whose
`confidence` field must be in [0, 1], which option gives the strongest
guarantee?

A. Tell the model "confidence must be 0–1" in the system prompt.
B. Use `tool_choice` forced to the emit tool, schema includes `"minimum": 0,
   "maximum": 1`, and a downstream `jsonschema` validator with retry on
   violation.
C. Strip violating outputs and continue silently.
D. Switch to extended thinking mode.

---

**Q6.** A simple intent classifier (4 classes, 1-token output) runs at 50 RPS
in production. A teammate suggests adding chain-of-thought "to improve
accuracy." Why is that probably wrong?

A. CoT is incompatible with classification.
B. CoT adds latency and cost without measurable accuracy gain on simple
   pattern-match tasks; reserve it for multi-step reasoning.
C. CoT requires extended thinking enabled, which Sonnet doesn't support.
D. CoT outputs are not parseable.

---

**Q7.** You want the model to reason carefully but only **return the final
answer** to the application. The best output shape is:

A. JSON with a `"reasoning"` field; strip it client-side.
B. `<thinking>...</thinking><answer>{...}</answer>`; parse only the `<answer>`
   block.
C. Markdown with an "Internal" section.
D. Print everything; let the UI hide reasoning with CSS.

---

**Q8.** A team ships a new prompt version for a contract-extraction task. They
"spot-checked 5 outputs and they look fine." Within a week, downstream pipeline
breaks on a class of inputs the old prompt handled correctly. What was missing?

A. Higher temperature.
B. A regression check against a stored labeled eval set before promoting the
   new prompt.
C. A larger model.
D. A retry loop.

---

**Q9.** Your few-shot examples are mostly happy-path classifications. The model
performs well on common inputs but **poorly on edge cases** (ambiguous, mixed-
signal). The best change is:

A. Add 10 more happy-path examples.
B. Replace 1–2 of the current examples with edge-case demonstrations that show
   how to handle ambiguity (e.g. "if both signals present → REVIEW").
C. Add temperature.
D. Switch to JSON output.

---

**Q10.** Which of the following is the **most production-grade** structured-
output design?

A. Free-form prose; downstream regex extraction.
B. Forced tool-use with a JSON-schema'd `input_schema` + a validate-and-retry
   loop in the application that surfaces concrete errors back to the model.
C. JSON-in-prose with a "Please be careful" system instruction.
D. Markdown headers; downstream parser splits sections.

---

### Answers & Rationale

| Q  | Ans | Why                                                                                            |
|----|-----|------------------------------------------------------------------------------------------------|
| 1  | B   | Forced tool-use is the canonical "no malformed JSON" lever.                                    |
| 2  | B   | Dynamic few-shot beats static when the example space is large; static caps out quickly.        |
| 3  | B   | Persona belongs in `system`; user role is for the request.                                     |
| 4  | B   | Concrete error feedback is the lever in validation retries; vague retries don't help.          |
| 5  | B   | Defense in depth: tool-use schema + downstream validator + retry on violation.                 |
| 6  | B   | CoT pays for itself on multi-step tasks; on classifiers it just adds cost.                     |
| 7  | B   | Tagged reasoning + tagged answer; parse only the answer block.                                 |
| 8  | B   | Prompts are code — labeled eval sets are the regression check; spot-checks miss tail cases.    |
| 9  | B   | Replace with edge-case examples; quantity past ~5 plateaus, edge-case coverage doesn't.        |
| 10 | B   | Schema enforcement at the API + business-invariant validation + retry = production shape.      |

---

## 4.11 Mini-Lab — Build a Hardened Classifier

**Goal:** A `classify_ticket(text) -> dict` function that:

1. Uses PRECISE-structured system prompt with 3 few-shot examples per class.
2. Forces tool-use output against a schema with explicit invariants
   (priority enum, confidence in [0, 1]).
3. Validates with `jsonschema` and retries up to 2× on failure with concrete
   error feedback.
4. Has an evaluation script that runs against a labeled `tickets.jsonl` and
   reports per-class accuracy + a failure bucket.
5. Has prompt caching enabled so the system prompt is hot.

**Skeleton (`classify.py`):**

```python
import json, time
from anthropic import Anthropic
from jsonschema import Draft202012Validator
client = Anthropic()

CATEGORIES = ["billing", "shipping", "technical", "account", "other"]
SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasoning": {"type": "string", "maxLength": 240},
    },
    "required": ["category", "priority", "confidence", "reasoning"],
    "additionalProperties": False,
}

SYSTEM = [
    {
        "type": "text",
        "text": """\
# PERSONA
You are a customer-support triage analyst. You are concise and evidence-driven.

# REQUEST
Classify the ticket into ONE category, assign a priority, and emit confidence + reasoning.

# CONTEXT
Categories: billing | shipping | technical | account | other.
Priority: low (FYI), medium (this week), high (today).

# EXAMPLES
<ticket>my package never arrived after 10 days</ticket>
{"category":"shipping","priority":"high","confidence":0.95,"reasoning":"Long delay; package missing."}

<ticket>can i change my email address?</ticket>
{"category":"account","priority":"low","confidence":0.92,"reasoning":"Self-service config question."}

<ticket>i was double-charged on my last invoice</ticket>
{"category":"billing","priority":"high","confidence":0.97,"reasoning":"Direct billing dispute."}

# EDGE CASES
- Mixed-signal tickets: pick the category by primary impact; output "medium".
- Empty/garbled input: category="other", priority="low", confidence<=0.3.
""",
        "cache_control": {"type": "ephemeral"},  # cache the system prompt
    },
]

validator = Draft202012Validator(SCHEMA)

def classify_ticket(text: str, max_retries: int = 2) -> dict:
    tools = [{"name": "emit", "description": "Emit the classification.",
              "input_schema": SCHEMA}]
    messages = [{"role": "user", "content": text}]

    for attempt in range(max_retries + 1):
        resp = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=512,
            system=SYSTEM, tools=tools,
            tool_choice={"type": "tool", "name": "emit"},
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})
        try:
            data = next(b.input for b in resp.content if b.type == "tool_use")
        except StopIteration:
            messages.append({"role": "user", "content": "Call emit."})
            continue
        errors = list(validator.iter_errors(data))
        if not errors:
            return data
        msg = "\n".join(f"- {e.message} at {'/'.join(map(str, e.path)) or '<root>'}"
                        for e in errors)
        messages.append({"role": "user", "content":
                         f"Validation errors:\n{msg}\nFix and re-emit."})
    raise RuntimeError("classify_ticket: validation retries exhausted")
```

**Eval script (`eval.py`):**

```python
import json, sys, collections
from classify import classify_ticket

def main(path="tickets.jsonl"):
    by_class = collections.defaultdict(lambda: [0, 0])  # [correct, total]
    failures = []
    for line in open(path):
        ex = json.loads(line)
        pred = classify_ticket(ex["text"])
        ok = pred["category"] == ex["category"]
        c = ex["category"]
        by_class[c][1] += 1
        if ok:
            by_class[c][0] += 1
        else:
            failures.append({"text": ex["text"], "want": ex["category"], "got": pred})
    print(f"{'class':<12} acc")
    for c, (correct, total) in by_class.items():
        print(f"{c:<12} {correct/total:.2%}")
    print(f"\n{len(failures)} failures")
    json.dump(failures, open("failures.json", "w"), indent=2)

if __name__ == "__main__":
    main(*sys.argv[1:])
```

**Stretch goals:**
- Add dynamic few-shot: embed `tickets.jsonl`, retrieve top-3 nearest at request time.
- Add a `priority_calibrator` second pass that re-checks `priority` against a
  rules-based threshold using the model's `confidence`.
- Wrap with API-retry on 429/5xx with exponential backoff.

---

## 4.12 Domain 4 Cheatsheet (flashcard-ready)

```
══════════════════════════════════════════════════════════════════════════
DOMAIN 4 — PROMPT ENGINEERING & STRUCTURED OUTPUT   (20%)
══════════════════════════════════════════════════════════════════════════

CORE FRAME
  A prompt is an INTERFACE CONTRACT.
  Validate model output like untrusted user input.
  Examples > exhortation. System ≠ user.

PRECISE FRAMEWORK
  P  Persona / role  (system role)
  R  Request          (single atomic task)
  E  Examples         (few-shot, 2-5)
  C  Context          (constraints, data, knowledge)
  I  Instructions     (numbered steps)
  S  Schema           (JSON / XML output spec)
  E  Edge cases       (explicit fallbacks)

ROLES
  system    persona, schema, examples, invariants
  user      the request, the data, the question
  assistant past turns, few-shot canned outputs, PRE-FILL trick

PRE-FILL TRICK
  Add a partial assistant message ("{") to force JSON;
  output does NOT include the prefill — concat back before parsing.

STRUCTURED OUTPUT — three levels
  L1  prose schema + prefill `{`           ~95% reliable
  L2  forced tool_use w/ input_schema      ~99% reliable
  L3  L2 + jsonschema validate + retry     production

VALIDATE-AND-RETRY (the pattern)
  on failure: surface the CONCRETE error path + message to the model
  retry up to N (2-3); fail loudly after; log inputs
  TWO retry layers: API (429/5xx, backoff) + Validation (semantic)

FEW-SHOT
  2 > 1, 3 > 2, ~5 plateaus
  match output FORMAT exactly (incl. punctuation/case)
  cover edge cases, not just happy path
  large example space → DYNAMIC few-shot (embed + top-k)

CHAIN-OF-THOUGHT
  zero-shot:  "Think step by step before answering."
  structured: <thinking>…</thinking><answer>…</answer>  ← production
  extended thinking: API-managed reasoning blocks
  USE for multi-step reasoning; SKIP for simple classification

SYSTEM PROMPT STRUCTURE
  1 persona  2 capabilities/limits  3 tools usage
  4 schema   5 tone   6 examples
  7 edge cases  8 refusal policy

OUTPUT FORMATS — pick one
  JSON via tool_use   ← production structured
  XML tags            ← reasoning + answer split
  Pre-fill + stop_seq ← streaming JSON
  Prose               ← UX text only

EVALUATION
  Stored labeled eval set; new prompt must equal-or-beat prior.
  Spot-checks are NOT sufficient; that's how regressions ship.

ANTI-PATTERNS (instant-wrong on exam)
  ✗ Persona in user role
  ✗ "Please return JSON" as the only enforcement
  ✗ Vague retries ("try again")
  ✗ Spot-check instead of eval set
  ✗ CoT on simple classifiers
  ✗ Negation-only rules ("don't X") with no positive
  ✗ More examples > better examples
  ✗ System prompt rewriting state every turn
  ✗ Letting business invariants ride on prompt prose alone

QUICK-CHOOSER
  malformed JSON           → forced tool_use (L2)
  semantic invariants      → L2 + jsonschema retry (L3)
  large example corpus     → dynamic few-shot
  multi-step reasoning     → CoT (structured tags)
  reasoning hidden         → <thinking>...</thinking><answer>...</answer>
  prompt change verified   → labeled eval set + regression check
══════════════════════════════════════════════════════════════════════════
```

---

> Next: **Domain 5 — Context Management & Reliability (15%)**. Token budgets,
> prompt caching (ephemeral & persistent), CALM framework, RAG patterns, and
> the long-conversation strategies that make or break production reliability.
