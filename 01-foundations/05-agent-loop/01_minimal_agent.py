import subprocess
import anthropic
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

client = anthropic.Anthropic()

TOOLS = [
    {
        "name": "bash",
        "description": "Run a bash command",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    }
]


def agent(goal: str) -> str:
    messages = [{"role": "user", "content": goal}]

    for _ in range(10):
        response = client.messages.create(
            model="claude-sonnet-4-6", max_tokens=4096, messages=messages, tools=TOOLS
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return response.content[0].text  # type: ignore[no-any-return]

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  -> Tool: {block.name}({block.input})")
                # Human-in-the-loop confirmation before executing
                if input("  Approve? (y/n): ").strip().lower() != "y":
                    return "Cancelled by user."
                result = subprocess.run(
                    block.input["command"], shell=True, capture_output=True, text=True, timeout=30
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result.stdout or result.stderr,
                    }
                )
        messages.append({"role": "user", "content": tool_results})  # type: ignore[dict-item]

    return "Max iterations reached"


if __name__ == "__main__":
    print("Minimal Agent (type 'quit' to exit)")
    print("Try: 'Summarize content for file in the current directory' or 'What OS am I running?'")
    while True:
        task = input("\nYou: ").strip()
        if task.lower() in ("exit", "quit", "q", ""):
            break
        print(f"\nAgent: {agent(task)}")
