# Domain 3: Claude Code Config & Workflows (20% of CCA-F)

> ~12 of 60 questions. Tied with Prompt Engineering for the second-largest weight.
> The exam treats Claude Code as a **first-class production system**, not a dev
> toy. Expect questions about CLAUDE.md precedence, hook firing order, permission
> resolution, and how to wire Claude Code into CI/CD with non-interactive runs.

---

## 3.0 Mental Model — Claude Code Is an Agent

The single most clarifying frame for this domain:

> **Claude Code is a hub-and-spoke agentic system whose system prompt is your
> CLAUDE.md, whose tools are bash + file editors + MCP servers, and whose
> orchestrator runs on your laptop.**

Everything in this domain is configuration of that agent:

| Knob                            | What it controls                                  |
|---------------------------------|---------------------------------------------------|
| `CLAUDE.md` files               | The system prompt (memory)                        |
| `settings.json` (3 scopes)      | Permissions, env, hooks, model                    |
| Slash commands (`.claude/commands/`) | Reusable user-prompt templates                |
| Hooks                           | Deterministic shell commands tied to events      |
| MCP servers                     | External tools (Domain 2)                        |
| Agents (`.claude/agents/`)      | Subagent definitions (Domain 1)                  |
| Claude Code SDK                 | Programmatic, headless invocation                 |

A common exam framing is "how do you make Claude *always* X?" The answer is
almost never "tell it to in CLAUDE.md" — that's a *suggestion*. For an
**enforced** behavior you need a **hook**.

> **Memorize:** CLAUDE.md is advisory. Hooks are mandatory. Permissions are
> the gate. The SDK is for headless. Slash commands are reusable prompts.

---

## 3.1 The CLAUDE.md Hierarchy

CLAUDE.md is loaded into the system prompt at session start. Multiple files
*compose*; they don't override.

### The four locations (in load order)

| # | Location                              | Scope                       | Use for                                      |
|---|---------------------------------------|-----------------------------|----------------------------------------------|
| 1 | `~/.claude/CLAUDE.md`                 | User (all projects)         | Personal preferences, default style          |
| 2 | `<repo>/CLAUDE.md`                    | Project (committed)         | Project conventions everyone shares          |
| 3 | `<repo>/CLAUDE.local.md`              | Project (gitignored)        | Local overrides, secrets-shaped notes        |
| 4 | `<subdir>/CLAUDE.md`                  | Sub-tree                    | Module-specific conventions                  |

When you're working in a subdirectory, **all four** are available; Claude Code
discovers them by walking up. The closer-to-the-cwd file appears later, so
it's the most contextually relevant.

### Composition (NOT override)

CLAUDE.md files are **concatenated** with origin labels. A statement in user
CLAUDE.md is not silenced by a project CLAUDE.md saying the opposite — both
end up in the prompt, and the model has to reconcile them.

> **Exam gotcha #1:** "How do I disable a rule from user CLAUDE.md inside one
> project?" The wrong-but-tempting answer is "rewrite it in project CLAUDE.md."
> The right answer is **explicitly negate it**: write *"Ignore the user-level
> rule about X for this project, because Y."* The model needs the contradiction
> spelled out.

### What belongs in each file

```
~/.claude/CLAUDE.md          (user, ~50 lines max)
  - Your name / role / experience level (helps tone)
  - Universal preferences (terse responses, no emojis, etc.)
  - Personal shortcuts you use across all projects

<repo>/CLAUDE.md             (project, committed, ~150-300 lines)
  - The product / repo's purpose in 2 sentences
  - The dev workflow (build, test, deploy commands)
  - Architectural invariants ("we don't import X from Y")
  - Test/lint commands the agent should run before declaring done
  - Where to look (paths, key modules, entry points)

<repo>/CLAUDE.local.md       (project, gitignored)
  - Personal credentials/aliases
  - Local-only feature flags
  - "Currently working on branch X" notes

<repo>/services/auth/CLAUDE.md   (sub-tree)
  - Conventions specific to this module
  - Inherited rules need not be repeated
```

### What does NOT belong in CLAUDE.md (exam-tested)

- **Hard rules.** "Never push to main." A rule that *must* hold belongs in a
  `PreToolUse` hook denying the bash command, not in prose.
- **Secrets.** Tokens, keys, DSNs — never. Even in `CLAUDE.local.md`, prefer
  env vars referenced from settings.
- **Long policy docs.** A 2,000-line policy file kills the context budget and
  pollutes every session. Reference it via a *resource* (Domain 2) or
  on-demand `Read`.
- **Dynamic state.** "Today we're working on issue #421." That belongs in the
  conversation, not the system prompt.

### CLAUDE.md gotchas

| Symptom                                    | Likely cause                              | Fix                                       |
|--------------------------------------------|-------------------------------------------|-------------------------------------------|
| Claude ignores a rule                      | Buried in a 1,000-line file               | Tighten + lift to top                     |
| Conflicting behavior between team members  | Each has their own user CLAUDE.md         | Move shared rules to project CLAUDE.md    |
| Claude leaks secrets in commits            | Secret stored in CLAUDE.md                | Move to env / hooks; add a hook to scrub  |
| New session can't find the build command   | Build command only in subdir CLAUDE.md    | Lift to project root or `/init`-style cmd |

### `/memory` and the `#` prefix

When a user types text starting with `#` in the prompt, Claude Code asks
*which CLAUDE.md to add it to*. This is the canonical way to grow CLAUDE.md
mid-session. The `/memory` slash command opens the active CLAUDE.md set in
your editor.

> **Exam gotcha #2:** "How does the user persist a new convention without
> editing files manually?" → `# <statement>` in the prompt; choose the scope.
> Distractors: "say it again next time" (transient), "add to settings.json"
> (wrong file).

---

## 3.2 Settings — Three Scopes, One Resolution Order

`settings.json` stores **non-prompt** configuration: permissions, env vars,
hooks, model selection, MCP servers (alternative to `.mcp.json`).

| Scope          | File                                          | Committed? | Resolution priority |
|----------------|-----------------------------------------------|------------|----------------------|
| User           | `~/.claude/settings.json`                     | No (private) | Lowest             |
| Project        | `<repo>/.claude/settings.json`                | **Yes**    | Middle               |
| Local override | `<repo>/.claude/settings.local.json`          | **No** (gitignored) | Highest    |

Resolution: local > project > user. **Arrays merge** (permissions concat);
**scalars override** (e.g. `model`).

### Skeleton with every meaningful field

```jsonc
{
  // Model selection (exam-relevant; can be set per-project)
  "model": "claude-opus-4-7",

  // Permission model — see §3.3
  "permissions": {
    "allow":  ["Bash(npm test:*)", "Bash(npm run build)", "Read", "Edit", "Glob", "Grep"],
    "deny":   ["Bash(rm -rf*)", "Bash(git push --force*)"],
    "ask":    ["Bash(git push:*)", "WebFetch"]
  },

  // Env vars exposed to the agent
  "env": { "NODE_ENV": "development", "DEBUG": "true" },

  // Hooks — see §3.5
  "hooks": {
    "PreToolUse":  [ /* ... */ ],
    "PostToolUse": [ /* ... */ ],
    "UserPromptSubmit": [ /* ... */ ],
    "Stop": [ /* ... */ ],
    "SubagentStop": [ /* ... */ ]
  },

  // MCP servers (alternative to .mcp.json; useful when you want
  // user-scope MCPs that aren't in any repo)
  "mcpServers": {
    "github": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"] }
  }
}
```

### Where to put what (exam shortcut)

| Setting                            | Best scope                    | Why                                       |
|------------------------------------|-------------------------------|-------------------------------------------|
| Project-wide allow/deny rules      | `project` settings, committed | Team consistency                          |
| Personal "ask" tweaks              | `user` settings               | Don't override teammates                  |
| Hot-fix "allow this one bash"      | `local` settings              | Doesn't pollute repo / team               |
| Model used for this codebase       | `project` settings            | Cost discipline                           |
| Personal style preferences         | `user` settings               | Personal                                  |
| Hook that enforces team policy     | `project` settings, committed | Otherwise it's just a suggestion         |

> **Exam gotcha #3:** "Permission X works for me but my teammate gets a prompt
> for it." → You added it to `settings.local.json`; move it to project
> `settings.json` (or to user settings if you want it personal).

---

## 3.3 Permission Model — `allow` / `deny` / `ask`

The permission system is the **gate** between the agent and your machine.

### The three lists

| List   | Behavior                                                                 |
|--------|--------------------------------------------------------------------------|
| `allow`| Tool runs without prompting                                              |
| `deny` | Tool is blocked outright; not even a prompt                              |
| `ask`  | Tool prompts the user (default for unlisted tools depending on mode)     |

`deny` is **strongest**: a tool listed in both `allow` and `deny` is denied.

### Permission patterns — exact-match vs prefix vs glob

```jsonc
{
  "permissions": {
    "allow": [
      "Bash(npm test)",          // exact command
      "Bash(npm test:*)",        // any subcommand of `npm test`
      "Bash(git status:*)",
      "Read",                    // entire tool, all inputs
      "Edit(src/**/*.ts)",       // glob over tool input — only this path
      "WebFetch(domain:docs.anthropic.com)"  // domain matcher (typed)
    ],
    "deny": [
      "Bash(rm -rf*)",           // catch-all destructive
      "Bash(git push --force*)",
      "Edit(/etc/**)",           // refuse to touch system files
      "Read(.env)", "Read(.env.*)" // never read secrets
    ],
    "ask": [
      "Bash(git push:*)",
      "Bash(npm publish:*)",
      "Bash(gh pr merge:*)"
    ]
  }
}
```

### Permission modes (`/permission-mode` or session flag)

| Mode                | What it does                                                       |
|---------------------|--------------------------------------------------------------------|
| `default`           | Honor `allow` / `deny` / `ask`; unlisted prompts                  |
| `acceptEdits`       | Auto-accept all file edits but still prompt for shells/network    |
| `plan`              | Read-only — agent cannot edit/exec until `ExitPlanMode`           |
| `bypassPermissions` | DANGEROUS: skip prompts entirely. Use only in sandboxed CI         |

### CI/CD recipe (exam)

In CI you cannot answer prompts. Two valid setups:

1. Concretely allowlist every tool/command needed in `settings.json` (committed).
2. Run with `--permission-mode bypassPermissions` **inside an isolated container
   without secrets** that you've already audited.

The exam-favored answer for production CI is **#1** — explicit allowlists. `bypass`
in CI is acceptable but risky and should be reserved for sandboxes.

### Common permission mistakes

| Mistake                                                | Consequence                              | Fix                                |
|--------------------------------------------------------|------------------------------------------|------------------------------------|
| `Bash` allowed unconditionally                         | Agent can run anything                   | Constrain by command pattern       |
| Secrets in repo readable by agent                      | Tokens leak into model context           | `deny` `Read(.env*)`               |
| `WebFetch` open                                        | Exfiltration risk                        | Restrict to domains                |
| Allow / deny conflict, expecting allow to win          | Tool fails silently                      | Remember: deny wins                |

---

## 3.4 Custom Slash Commands

Slash commands are **reusable prompt templates**, stored as Markdown files.

### Locations

```
~/.claude/commands/<name>.md         # personal, all projects
<repo>/.claude/commands/<name>.md    # project, committed
<repo>/.claude/commands/team/foo.md  # namespaced — invoked as /team:foo
```

A user typing `/<name>` injects the file's contents into the conversation as
a user message, with `$ARGUMENTS` substituted from anything typed after the
command.

### Anatomy of a slash command (with frontmatter)

```markdown
---
description: "Run the full PR review checklist"
allowed-tools: ["Bash(npm test:*)", "Read", "Grep", "Glob"]
argument-hint: "[base-branch]"
---

You are about to review a PR. Base branch: $ARGUMENTS (default: main).

Steps:
1. Run `git diff $ARGUMENTS...HEAD` and read the full diff.
2. Identify any new files; read each.
3. Run `npm test` and confirm it passes.
4. Produce a review with three sections: SHIP-BLOCKERS, NITS, KUDOS.
```

The `allowed-tools` frontmatter narrows permissions for the duration of this
command — useful when a slash command should *not* be able to push or write
files.

### When to use what

| Need                                 | Mechanism                       |
|--------------------------------------|---------------------------------|
| Reusable prompt template             | Slash command                   |
| Reusable prompt + tool restrictions  | Slash command + `allowed-tools` |
| Reusable agent personality           | Subagent (`.claude/agents/`)    |
| Side-effect on every event           | Hook                            |
| Programmatic invocation from a script| SDK                             |

### Exam pitfalls

- Slash commands are *prompts*, not *agents*. They run in the same context as
  the parent conversation, share its tools, and don't have isolated state.
- `$ARGUMENTS` is the **whole** trailing string. If you need positional args
  with parsing, do it in the command body via Bash + jq, not via templating.
- Slash commands cannot enforce behavior; the model can decide not to follow
  them. For enforcement, use hooks.

---

## 3.5 Hooks — The Only Way to Make Claude Code "Always Do X"

Hooks are deterministic shell commands tied to lifecycle events. The runtime
executes them — Claude does not. This is why hooks are the only way to
**guarantee** behavior.

### Hook events (exam favorites in bold)

| Event                      | When it fires                                                       |
|----------------------------|---------------------------------------------------------------------|
| **`PreToolUse`**           | Before any tool call; can deny by exiting non-zero                  |
| **`PostToolUse`**          | After a tool call; sees the result                                  |
| `UserPromptSubmit`         | Just after the user presses enter                                   |
| `Stop`                     | When Claude finishes its turn                                       |
| `SubagentStop`             | When a subagent finishes                                            |
| `SessionStart` / `SessionEnd` | Once per session                                                |
| `Notification`             | When Claude needs attention (idle, awaiting permission, etc.)       |

### Hook config shape

```jsonc
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "scripts/audit-bash.sh" }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          { "type": "command", "command": "npx prettier --write \"$CLAUDE_TOOL_INPUT_path\"" }
        ]
      }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "scripts/notify-done.sh" } ] }
    ]
  }
}
```

### Hook control flow — exit codes & JSON output

A hook can:

- **Exit 0** → continue normally.
- **Exit 2** → block the tool call (for `PreToolUse`); the agent sees the
  hook's stderr as feedback.
- **Print JSON to stdout** → richer control: rewrite the input, attach extra
  context, redact, etc.

```bash
#!/usr/bin/env bash
# scripts/audit-bash.sh — block force pushes, log everything else
set -euo pipefail
input=$(cat)                                # JSON: tool name + input
cmd=$(echo "$input" | jq -r '.tool_input.command')
if echo "$cmd" | grep -qE 'git push.*--force'; then
  echo "Force push blocked by policy." >&2
  exit 2                                    # block the tool call
fi
echo "$cmd" >> .claude/audit.log
exit 0
```

### Three exam-favorite hook patterns

**1. Auto-format after edit** — guaranteed, not "please remember":

```jsonc
"PostToolUse": [{
  "matcher": "Edit|Write|MultiEdit",
  "hooks": [{ "type": "command",
              "command": "npx prettier --write \"$CLAUDE_TOOL_INPUT_path\" 2>/dev/null || true" }]
}]
```

**2. Block dangerous bash before it runs**:

```jsonc
"PreToolUse": [{
  "matcher": "Bash",
  "hooks": [{ "type": "command", "command": "scripts/deny-dangerous.sh" }]
}]
```

**3. Notify when Claude finishes** (so it doesn't sit idle):

```jsonc
"Stop": [{ "hooks": [{ "type": "command", "command": "osascript -e 'display notification \"Claude done\"'" }] }]
```

### Hook gotchas

- Hooks run in **your shell with your env** — they can do anything you can.
  Treat them like cron entries. Audit before installing community settings.
- A `PostToolUse` hook that hangs **stalls the agent**. Background long
  operations (`&` + redirect) or use timeouts.
- Hooks see `CLAUDE_TOOL_INPUT_<field>` env vars and JSON on stdin; pick one
  style and stick with it.
- `UserPromptSubmit` hooks can **prepend extra context** to the prompt. This
  is the canonical way to inject dynamic project state (current branch, last
  test status) without putting it in CLAUDE.md.

### "How do I make Claude *always* X" cheat sheet

| Want                                              | Mechanism                                  |
|---------------------------------------------------|--------------------------------------------|
| Format on save                                    | `PostToolUse` hook                         |
| Block force pushes                                | `PreToolUse` hook OR `deny` permission     |
| Run tests before commit                           | `PreToolUse` hook on Bash matching `git commit` |
| Prepend current branch to every prompt            | `UserPromptSubmit` hook printing context   |
| Audit every shell command                         | `PreToolUse` hook + log                    |
| Refuse network calls                              | `deny` `WebFetch` and bash patterns        |
| Send a Slack message when Claude is done          | `Stop` hook                                |
| Reload context after a long-running build         | `PostToolUse` hook + injected reminder     |

---

## 3.6 Subagents (`.claude/agents/`)

Subagent definitions are Markdown files that bundle a system prompt + tool
allowlist + model into a named persona. The orchestrator invokes them via the
`Agent` tool with `subagent_type: <name>`.

```
.claude/agents/
  reviewer.md
  test-runner.md
  release-notes.md
```

Skeleton:

```markdown
---
name: reviewer
description: "Code reviewer that produces SHIP-BLOCKER / NIT / KUDOS reports."
model: sonnet
allowed-tools: ["Read", "Grep", "Glob", "Bash(git diff:*)", "Bash(npm test:*)"]
---

You are a code reviewer.
Output exactly three sections: SHIP-BLOCKERS, NITS, KUDOS.
Quote file:line for each item.
Don't suggest unrelated refactors.
```

### Agent vs slash command (exam-tested)

| Feature                      | Subagent                          | Slash command                         |
|------------------------------|-----------------------------------|---------------------------------------|
| Isolated context             | **Yes** (own message history)     | No (parent context)                   |
| Own model / tool list        | Yes                               | Restricted via `allowed-tools` only   |
| Persona / system prompt      | Yes                               | No (just a user prompt)               |
| Returns to parent            | Single summary message            | N/A — runs inline                     |
| Right for                    | Specialized, parallelizable work  | Reusable prompts                      |

### Pattern: parallel subagents from the orchestrator

The exam tests this Domain 1 pattern through the Domain 3 lens: when you want
parallel work in Claude Code, you do *not* hand-craft a Python orchestrator —
you let the parent agent invoke the `Agent` tool multiple times in parallel.
Each subagent has its own `.claude/agents/<name>.md` definition.

---

## 3.7 Claude Code SDK — Headless / Programmatic Use

The SDK is for **invoking Claude Code from a script or CI job** without an
interactive UI. It exposes the same agent loop, tools, hooks, and config —
just driven programmatically.

### Why the SDK matters on the exam

- CI/CD pipelines that run code review, generate release notes, or triage issues.
- Internal automations (Slack bot calls Claude Code, Claude Code drives a build).
- Anywhere you'd otherwise put `claude --print` in a shell script.

### Two modes

| Mode             | Stub command           | When to use                                       |
|------------------|------------------------|---------------------------------------------------|
| **One-shot**     | `claude -p "<prompt>"` | Single prompt, single output, exit                |
| **Multi-turn**   | SDK `query()` / agent loop | Long-running automation, conversational state |

### Python SDK skeleton (one-shot)

```python
"""
ci_review.py — non-interactive Claude Code invocation in CI.

WHY this shape:
  * `--output-format=stream-json` lets us parse intermediate events for
    logging without running an interactive TTY.
  * `--permission-mode acceptEdits` is appropriate when CI mutates files
    in a sandboxed container and we trust the diff to be reviewed before merge.
  * settings.json in the repo defines the allow/deny rules; we do NOT
    rely on bypass.
"""
import json, subprocess, sys

prompt = """
Review the changes on this branch vs origin/main.
Run `npm test` and verify pass.
Produce a markdown review with sections SHIP-BLOCKERS / NITS / KUDOS.
"""

proc = subprocess.run([
    "claude", "-p", prompt,
    "--output-format", "stream-json",
    "--permission-mode", "acceptEdits",
    "--max-turns", "20",
], capture_output=True, text=True, timeout=900)

# stream-json emits one JSON object per line (assistant turns, tool calls, etc.)
events = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
final = next((e for e in reversed(events) if e.get("type") == "result"), None)
print(final["result"] if final else "[no result]", file=sys.stdout)
sys.exit(0 if proc.returncode == 0 else 1)
```

### TypeScript SDK skeleton

```typescript
// review.ts
import { query } from "@anthropic-ai/claude-agent-sdk";

for await (const msg of query({
  prompt: "Review this branch vs main. Run tests. Output markdown review.",
  options: {
    permissionMode: "acceptEdits",
    maxTurns: 20,
  },
})) {
  if (msg.type === "result") console.log(msg.result);
}
```

### CI/CD integration recipe (the exam will ask)

```yaml
# .github/workflows/claude-review.yml
name: Claude review
on: pull_request
jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }            # we need full history for diff
      - uses: actions/setup-node@v4
        with: { node-version: 20 }
      - run: npm ci
      - name: Install Claude Code
        run: npm i -g @anthropic-ai/claude-code
      - name: Run review
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          claude -p "Review the diff vs origin/${{ github.base_ref }}; output markdown" \
            --output-format text \
            --permission-mode acceptEdits \
            --max-turns 15 \
            > review.md
      - name: Post review
        uses: peter-evans/create-or-update-comment@v4
        with:
          issue-number: ${{ github.event.pull_request.number }}
          body-path: review.md
```

### Failure modes to know

| Symptom                                 | Cause                                       | Fix                                       |
|-----------------------------------------|---------------------------------------------|-------------------------------------------|
| CI hangs forever                        | Tool prompt with no answerer                | Allowlist all tools or `bypass` carefully  |
| "Permission denied" mid-job             | Missing rule in committed settings.json     | Add to project `settings.json`            |
| OOM / runaway cost                      | No `--max-turns` cap                        | Add cap; cap iterations                   |
| Inconsistent output between runs        | No `temperature=0`, no fixed model pin      | Pin model + add system prompt rigor       |
| Secrets in transcript                   | Hooks/SDK printed env                       | Redact in hook output                     |

### Output formats

| `--output-format` | Use case                               |
|-------------------|----------------------------------------|
| `text` (default)  | Final answer only                      |
| `json`            | Final answer + metadata, single object |
| `stream-json`     | One JSON event per line (live)         |

---

## 3.8 Persistent Project Context — Where State Lives

| Where                              | Survives sessions? | Survives `git clean`? | Use for                        |
|------------------------------------|-------------------|----------------------|--------------------------------|
| `CLAUDE.md` (committed)            | Yes               | Yes                  | Conventions                    |
| `CLAUDE.local.md`                  | Yes               | Yes if .gitignored   | Local notes                    |
| `~/.claude/projects/<...>/memory/` | Yes               | Yes                  | Auto-memory across sessions    |
| `.claude/settings.json`            | Yes               | Yes                  | Permissions/hooks/MCP          |
| `.claude/commands/`                | Yes               | Yes                  | Slash command templates        |
| Conversation transcript            | No                | n/a                  | Ephemeral state                |

### Auto-memory directory (system-managed)

Claude Code maintains a per-project memory directory at
`~/.claude/projects/<project-slug>/memory/` containing classified memories
(user / project / feedback / reference). This is **not** the same thing as
CLAUDE.md — it's structured, lazily loaded, and updated by the agent itself
(if the auto-memory feature is enabled).

### Exam pitfall

> "How do you persist that the user prefers tabs over spaces across sessions
> for *this project only*?" → write it to `<repo>/CLAUDE.md` (project, all
> teammates) or `<repo>/CLAUDE.local.md` (project, you only). User-level
> memory affects all projects; conversation memory dies on exit.

---

## 3.9 Architecture Decision Frameworks

### Framework A — "How do I make Claude do X?"

```
Is X a STATEMENT of preference / convention?
    YES → CLAUDE.md (project for team, user for personal)
Is X a REUSABLE prompt or workflow?
    YES → slash command (with allowed-tools if scoping)
Is X a GUARANTEED behavior on every event?
    YES → hook
Is X a DOMAIN-SPECIALIZED persona/role?
    YES → subagent in .claude/agents/
Is X a CAPABILITY (read DB, call API)?
    YES → tool / MCP server (Domain 2)
Is X a HARD GATE (block force-push)?
    YES → permissions deny + hook for safety net
```

### Framework B — Settings scope chooser

```
Should EVERY teammate get this?
    YES → project settings.json (committed)
Is this PERSONAL TASTE only?
    YES → user ~/.claude/settings.json
Is this a TEMPORARY OR LOCAL OVERRIDE?
    YES → settings.local.json
Does this contain a SECRET?
    YES → env var, NOT settings.json — reference via ${env:NAME}
```

### Framework C — Slash command vs subagent vs hook

| Need                                   | Mechanism      | Why                                     |
|----------------------------------------|----------------|-----------------------------------------|
| "I run the same prompt 5×/day"         | Slash command  | Cheap, in-context                       |
| "We need a focused reviewer persona"   | Subagent       | Isolated context + scoped tools         |
| "Format every file after edit"         | Hook           | Deterministic, runs every time          |
| "Inject current branch into prompts"   | Hook (`UserPromptSubmit`) | Dynamic context injection    |
| "Refuse all `rm -rf`"                  | Permission deny + hook | Defense in depth                |

---

## 3.10 Practice MCQs (Domain 3)

---

**Q1.** Your team standardizes on running `pnpm format` after every file edit.
You've added an instruction to project CLAUDE.md saying "always run pnpm format
after editing files," but **Claude only runs it about 70% of the time**. What's
the right fix?

A. Add the instruction to user CLAUDE.md as well so it's loaded twice.
B. Replace the instruction with a `PostToolUse` hook that runs `pnpm format`
   on the edited file path.
C. Increase `max_tokens` to give Claude more room.
D. Add `temperature=0` in settings.

---

**Q2.** A teammate added `Bash(rm -rf*)` to her **user** `settings.json`'s
`allow` list "for convenience." On a shared incident, her Claude session
deleted the wrong directory. Beyond reverting, what's the architectural fix?

A. Move the entry to project `settings.json` so the team can review it.
B. Add `Bash(rm -rf*)` to project `settings.json`'s `deny` list — `deny`
   beats `allow` regardless of scope.
C. Switch to bypassPermissions mode.
D. Tell teammates to read CLAUDE.md before sessions.

---

**Q3.** Your team wants Claude Code to **review every PR** in CI without
human intervention. Which is the production-grade setup?

A. `claude` interactive mode in CI; the runner answers permission prompts.
B. SDK invocation (`claude -p ... --output-format=stream-json --max-turns=N`)
   with explicit `permissions.allow` in committed `.claude/settings.json`.
C. Hard-code `--permission-mode bypassPermissions` for all CI jobs.
D. Build a custom MCP server that proxies the Anthropic API.

---

**Q4.** You want every prompt the user submits to be **automatically prefixed
with the current git branch and last commit SHA**, without modifying CLAUDE.md.
Which mechanism fits?

A. A slash command that the user types each turn.
B. A `UserPromptSubmit` hook that prints additional context to stdout.
C. A subagent that injects context.
D. Add the metadata to CLAUDE.md and re-load every session.

---

**Q5.** A repository has both `<repo>/CLAUDE.md` (team, "use TypeScript") and
`<repo>/services/legacy/CLAUDE.md` (sub-tree, "this module is JavaScript;
do not migrate"). When the user works inside `services/legacy/`, what does
Claude see?

A. Only the sub-tree CLAUDE.md (closer scope wins).
B. Only the project CLAUDE.md (project always wins).
C. Both files concatenated with origin labels; Claude must reconcile.
D. Whichever is alphabetically first.

---

**Q6.** A team's PR-review automation needs **strict reproducibility** for
audit. They run `claude -p "<prompt>"`. Which option group is most important?

A. Pin the model (`--model claude-sonnet-4-6`), pin tool allowlist in
   committed `.claude/settings.json`, set `--max-turns`, and use
   `--output-format json` for parseable output.
B. Use the latest model alias `claude-latest` and full `bypassPermissions`.
C. Run interactive mode and have the engineer click through.
D. Disable hooks to remove non-determinism.

---

**Q7.** You want a personal command `/standup` that posts your daily standup
to Slack. The command must be **available across all your projects** but **not
shared with teammates**. Where do you put the file?

A. `<repo>/.claude/commands/standup.md`
B. `~/.claude/commands/standup.md`
C. `<repo>/.claude/commands/personal/standup.md`
D. `~/.claude/CLAUDE.md`

---

**Q8.** Your `PreToolUse` hook on `Bash` runs a 30-second linter, and **the
agent stalls noticeably** between every shell call. What's the fix?

A. Move the lint logic into CLAUDE.md so the model self-checks.
B. Split the hook: keep a fast (<200ms) safety check synchronously; move the
   slow lint to a background process (`&`) or to `PostToolUse`.
C. Increase the agent's `max_tokens`.
D. Disable hooks entirely.

---

**Q9.** Your codebase has a `.env` file with a production database password.
You notice Claude Code reads it during a debugging session and the value ends
up in the assistant transcript. Which is the immediate, **architectural** fix?

A. Tell the user to be more careful next time.
B. Add `Read(.env)` and `Read(.env.*)` to `permissions.deny` in committed
   `.claude/settings.json`. Optionally rotate the secret.
C. Encrypt `.env` with GPG.
D. Move all environment variables into CLAUDE.md.

---

**Q10.** Which of the following is a **valid use case for a subagent
(`.claude/agents/`)** rather than a slash command?

A. A reusable "explain this PR" prompt that runs in the same context.
B. A specialized code-reviewer with its own system prompt, isolated context,
   and a restricted tool set, invoked in parallel by the parent agent.
C. A request to format the user's input.
D. A way to inject env vars into the prompt.

---

### Answers & Rationale

| Q  | Ans | Why                                                                                            |
|----|-----|------------------------------------------------------------------------------------------------|
| 1  | B   | CLAUDE.md is advisory; hooks are mandatory. Format-on-save is the canonical hook example.    |
| 2  | B   | `deny` wins regardless of scope; defense in depth.                                              |
| 3  | B   | SDK with explicit allowlist is the audit-friendly, production-grade CI setup.                   |
| 4  | B   | `UserPromptSubmit` hook prints additional context — the canonical dynamic-prefix pattern.       |
| 5  | C   | CLAUDE.md files compose, not override.                                                          |
| 6  | A   | Reproducibility = pinned model + pinned permissions + bounded turns + parseable output.        |
| 7  | B   | User scope (~/.claude/commands) — across projects, not shared.                                 |
| 8  | B   | Hooks are synchronous; long work belongs out of the critical path.                              |
| 9  | B   | Architectural fix is permission denial in committed settings; CLAUDE.md and politeness fail.    |
| 10 | B   | Isolated context + own system prompt + scoped tools = the subagent definition.                  |

---

## 3.11 Mini-Lab — A Production Claude Code Setup

**Goal:** Configure a fictional repo `payments-service` for a team of 8 engineers
so that:

1. Every engineer gets the same permissions, hooks, and MCP servers on clone.
2. Force-pushes to `main` are blocked architecturally.
3. Files are auto-formatted after every edit.
4. A Postgres MCP server is available, with the connection string referenced
   from `.env` (gitignored).
5. A custom slash command `/release-notes` generates release notes from
   `git log`.
6. A subagent `reviewer` runs PR reviews with a scoped tool list.
7. A CI job posts an automated review on every PR.

**Files to write:**

```
payments-service/
├── CLAUDE.md                            # team conventions
├── .mcp.json                            # postgres MCP w/ ${env:PG_DSN}
├── .gitignore                           # excludes .env, settings.local.json, CLAUDE.local.md
├── .claude/
│   ├── settings.json                    # permissions, hooks, model
│   ├── commands/
│   │   └── release-notes.md
│   └── agents/
│       └── reviewer.md
└── .github/workflows/claude-review.yml
```

**Skeleton: `.claude/settings.json`**

```jsonc
{
  "model": "claude-sonnet-4-6",
  "permissions": {
    "allow": [
      "Bash(npm test:*)", "Bash(npm run build)", "Bash(git diff:*)",
      "Bash(git log:*)", "Bash(git status:*)",
      "Read", "Glob", "Grep", "Edit(src/**)", "Edit(tests/**)"
    ],
    "deny": [
      "Bash(rm -rf*)", "Bash(git push --force*)",
      "Read(.env)", "Read(.env.*)"
    ],
    "ask": ["Bash(git push:*)", "WebFetch", "Edit(infra/**)"]
  },
  "hooks": {
    "PostToolUse": [{
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [{ "type": "command",
                  "command": "scripts/format.sh \"$CLAUDE_TOOL_INPUT_path\"" }]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{ "type": "command", "command": "scripts/audit-bash.sh" }]
    }]
  }
}
```

**Skeleton: `.claude/agents/reviewer.md`**

```markdown
---
name: reviewer
description: "Code reviewer for payments-service PRs."
model: sonnet
allowed-tools: ["Read", "Grep", "Glob", "Bash(git diff:*)", "Bash(npm test:*)"]
---

You are a payments-service code reviewer.

Output exactly three sections:
- SHIP-BLOCKERS
- NITS
- KUDOS

Quote file:line on each item. Don't suggest unrelated refactors.
```

**Skeleton: `.claude/commands/release-notes.md`**

```markdown
---
description: "Generate release notes from git log."
allowed-tools: ["Bash(git log:*)", "Read"]
argument-hint: "[since-tag]"
---

Generate release notes covering commits since $ARGUMENTS.
Group by: features, fixes, chores. Use bullet points.
```

**Stretch goals:**
- Add a `Stop` hook that posts the session summary to a Slack channel.
- Add a second subagent `security-reviewer` with `allowed-tools` restricted
  to read-only and Bash for Semgrep.
- Add a `UserPromptSubmit` hook that prepends the current branch name and
  the last `npm test` status.

---

## 3.12 Domain 3 Cheatsheet (flashcard-ready)

```
══════════════════════════════════════════════════════════════════════════
DOMAIN 3 — CLAUDE CODE CONFIG & WORKFLOWS    (20%)
══════════════════════════════════════════════════════════════════════════

THE FRAME
  Claude Code = hub-and-spoke agent
    system prompt = CLAUDE.md
    tools         = bash + edit + MCP servers
    config        = .claude/settings.json (3 scopes)
    automations   = hooks
    personas      = .claude/agents/
    SDK           = headless / programmatic

CLAUDE.md HIERARCHY (compose; closer ≠ wins, all are loaded)
  ~/.claude/CLAUDE.md             → user, all projects
  <repo>/CLAUDE.md                → project, committed
  <repo>/CLAUDE.local.md          → project, gitignored
  <subdir>/CLAUDE.md              → sub-tree
  Conflicts must be resolved EXPLICITLY in prose.

CLAUDE.md DOES NOT contain:
  - hard rules → use hooks or permissions
  - secrets   → use env vars
  - long policy docs → use resources or files
  - dynamic state → put in conversation

`#`-prefix prompt → adds line to CLAUDE.md (asks scope)

SETTINGS SCOPES (deny > allow; arrays merge; scalars override)
  user      ~/.claude/settings.json            personal
  project   <repo>/.claude/settings.json       team, committed
  local     <repo>/.claude/settings.local.json local override

PERMISSIONS
  allow / ask / deny ; deny WINS
  patterns: Bash(cmd), Bash(cmd:*), tool-only (Read), Edit(glob),
            WebFetch(domain:foo.com)
  Modes: default | acceptEdits | plan | bypassPermissions
  CI: explicit allowlist > bypass

SLASH COMMANDS (.claude/commands/)
  Markdown w/ frontmatter (description, allowed-tools, argument-hint)
  $ARGUMENTS = entire trailing string
  Reusable PROMPT — runs in parent context, NOT isolated

SUBAGENTS (.claude/agents/)
  Markdown w/ frontmatter (name, description, model, allowed-tools)
  Isolated context, own system prompt, returns single summary
  Use when: specialized persona OR parallelism OR strict tool scope

HOOKS — the only way to make Claude ALWAYS do X
  Events: PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop,
          SessionStart/End, Notification
  Exit 2 (PreToolUse) → block; stderr → fed to model
  JSON stdout → richer control (rewrite, redact, attach context)
  Hooks RUN IN YOUR SHELL — audit before installing community settings
  Long hooks stall the agent — background or move to PostToolUse

SDK (headless)
  claude -p "..." --output-format stream-json --max-turns N
  CI recipe: pinned model + committed allowlist + bounded turns + JSON output
  Output formats: text | json | stream-json
  ANTI-PATTERN: bypassPermissions in production CI

PERSISTENCE OF STATE
  CLAUDE.md (committed)        → conventions, all sessions
  CLAUDE.local.md (gitignored) → local notes
  .claude/settings.json        → permissions/hooks/MCP
  .claude/commands/, agents/   → shared automations
  ~/.claude/projects/.../memory → auto-memory (system-managed)
  Conversation                 → ephemeral

DECISION QUICK-CHOOSER
  enforce X always           → HOOK (or permission)
  reusable prompt template   → SLASH COMMAND
  specialized persona        → SUBAGENT
  team-wide config           → project settings.json (committed)
  personal taste             → user settings
  hard gate                  → permission deny
  dynamic context inject     → UserPromptSubmit hook
  CI/CD non-interactive      → SDK + explicit allowlist + max-turns

COMMON EXAM TRAPS
  ✗ Putting "always do X" in CLAUDE.md instead of a hook
  ✗ Allow without scoping ("Bash") — too broad
  ✗ Inlining tokens in committed settings
  ✗ bypassPermissions in production CI
  ✗ Expecting closer CLAUDE.md to override farther one
  ✗ Treating slash command as a subagent (no isolated context)
  ✗ Long synchronous hooks blocking the agent
  ✗ Reading .env without a deny rule
  ✗ Conflating .mcp.json (project) with mcpServers in user settings
══════════════════════════════════════════════════════════════════════════
```

---

> Next: **Domain 4 — Prompt Engineering & Structured Output (20%)**.
> JSON schema enforcement, PRECISE, validation retries, and the failure modes
> the exam rewards you for spotting.
