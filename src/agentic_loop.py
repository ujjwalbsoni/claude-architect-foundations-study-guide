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
            model="claude-haiku-4-5-20251001",
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