"""
Custom Promptfoo provider wrapping the research assistant.

Promptfoo calls call_api() for each test case. The function receives:
- prompt: the rendered prompt string
- options: dict with 'config' from YAML
- context: dict with 'vars' from the test case
"""


def call_api(prompt, options, context):
    """Promptfoo provider entry point."""
    from shared.knowledge_base import get_agent_response, EVAL_TASKS

    question = context.get("vars", {}).get("question", prompt)

    # Find matching task by question text
    task_id = None
    for task in EVAL_TASKS:
        if task["question"] == question:
            task_id = task["id"]
            break

    if task_id is None:
        return {"output": "No matching task found."}

    response = get_agent_response(task_id)

    return {
        "output": response["answer"],
        "tokenUsage": {"total": 100, "prompt": 50, "completion": 50},
    }
