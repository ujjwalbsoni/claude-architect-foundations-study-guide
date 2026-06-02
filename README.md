# Claude Certified Architect – Foundations (CCA-F) Study Guide

A production-grade, self-paced study course for Anthropic's **Claude Certified
Architect – Foundations** certification exam.

> **Exam:** 60 multiple-choice questions · 120 minutes · Passing score 720/1000 ·
> $99 · Online proctored · Scenario-based questions across 5 domains

This repo is the primary resource I built while preparing for the exam. Every
module is dense, scenario-anchored, and code-first. If you are studying for the
CCA-F, you can work straight through the [4-week study plan](Study_Plan_4_Week.md)
and reference each domain module as you go.

---

## What's inside

Each domain module follows the same structure:

1. **Concept explanation** — mental models and exam framings
2. **Runnable Python code** — full implementations using the `anthropic` SDK
   and the official `mcp` SDK; no pseudocode
3. **Architecture patterns** — decision frameworks and tradeoff tables
4. **Scenario-based MCQs** — 10 per domain, with full answer-key rationale
5. **Mini-lab** — a hands-on project to lock in the concepts
6. **Cheatsheet** — a flashcard-style summary of every key pattern, API, and
   anti-pattern from the domain

## Course modules (weighted by exam %)

| #  | Module | Exam weight | Topics |
|----|--------|------------:|--------|
| D1 | [Agentic Architecture & Orchestration](Domain_1_Agentic_Architecture.md) | **27%** | Agentic loop, hub-and-spoke, task decomposition, subagent coordination, **SPIDER** reliability pattern, autonomy tradeoffs |
| D2 | [Tool Design & MCP Integration](Domain_2_Tool_Design_MCP.md) | **18%** | Tool schema design, tool boundaries, **MCP transports (stdio vs SSE)**, auth patterns, resources, MCP client config |
| D3 | [Claude Code Config & Workflows](Domain_3_Claude_Code_Config.md) | **20%** | **CLAUDE.md hierarchy**, settings scopes, permission model, slash commands, subagents, hooks, Claude Code SDK, CI/CD |
| D4 | [Prompt Engineering & Structured Output](Domain_4_Prompt_Engineering.md) | **20%** | **PRECISE framework**, role prompting, JSON schema enforcement, few-shot, chain-of-thought, validate-and-retry loops |
| D5 | [Context Management & Reliability](Domain_5_Context_Management.md) | **15%** | Token budgets, **prompt caching** (ephemeral & 1-hour), **CALM framework**, multi-turn design, RAG sub-patterns, reliability primitives |
| —  | [4-Week Study Plan](Study_Plan_4_Week.md) | — | 28-day daily plan weighted by exam %, exam-day strategy, readiness checklist |

## How to use this repo

**If you have 4 weeks before the exam:** open [`Study_Plan_4_Week.md`](Study_Plan_4_Week.md)
and work through it day by day. Each day cites the exact domain subsections to
read and the labs to run.

**If you have less time:** read the cheatsheet at the bottom of each domain
module first, then drill the practice MCQs. The MCQs are written to mirror the
real exam's scenario-based format and distractor density.

**If you're cross-checking concepts:** every domain module has a quick-chooser
section at the end of its cheatsheet — useful for "what's the right architecture
for X" lookups.

## Setup

```bash
# Python 3.11+
pip install anthropic jsonschema mcp

# Claude Code (for Domain 3 labs)
npm install -g @anthropic-ai/claude-code

# Auth
export ANTHROPIC_API_KEY=sk-ant-...
```

Each domain's mini-lab is self-contained. The hands-on code from Day 1 of the
study plan lives in [`src/agentic_loop.py`](src/agentic_loop.py).

## Domain weights at a glance

```
D1 Agentic Architecture       ████████████████████████████  27%
D3 Claude Code Config         ████████████████████          20%
D4 Prompt Engineering         ████████████████████          20%
D2 Tool Design & MCP          ██████████████████            18%
D5 Context Management         ███████████████               15%
```

Time spent on each domain in the 4-week plan matches these weights.

## Exam-strategy notes baked into every module

- **Distractors are very plausible.** The exam tests architectural judgment
  under production constraints — every wrong answer is a thing that *sounds*
  reasonable. Each module's cheatsheet ends with an "instant-wrong" anti-pattern
  list to help you spot them.
- **Tradeoffs over definitions.** The MCQs are framed around real production
  scenarios; pick the leftmost autonomy / lowest blast radius / simplest
  architecture that meets the requirement.
- **Common failure points are flagged.** MCP tool boundaries, CLAUDE.md
  composition vs override, and "use a bigger context window" distractors are
  called out explicitly.

## Contributing

Found a mistake, a clearer phrasing, or a scenario MCQ you think belongs?
Open a PR or issue. Real-exam topic shifts will be reflected here as
Anthropic publishes updates to the certification.

## License

[MIT](LICENSE) — free to fork, remix, and use for your own prep. Not affiliated
with Anthropic; "Claude" and "Claude Code" are trademarks of Anthropic.
