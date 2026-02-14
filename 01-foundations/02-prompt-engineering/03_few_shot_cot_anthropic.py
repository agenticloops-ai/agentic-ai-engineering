"""
Few-Shot & Chain-of-Thought Prompting (Anthropic)

Compares four prompting strategies for classifying agent requests:
1. Zero-shot — no examples, no reasoning guidance
2. Few-shot — examples provided for in-context learning
3. Chain-of-thought — explicit reasoning steps before classification
4. Few-shot + CoT — examples with reasoning traces

Classification is directly relevant to agent routing in multi-agent systems.
"""

import anthropic
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from common import AnthropicTokenTracker, setup_logging

load_dotenv(find_dotenv())

logger = setup_logging(__name__)

CATEGORIES = "CODE_GENERATION, CODE_REVIEW, DEBUGGING, DOCUMENTATION, GENERAL_QUESTION"

# Few-shot examples for classification
CLASSIFICATION_EXAMPLES = [
    ("Write a Python function that sorts a list using merge sort", "CODE_GENERATION"),
    ("Check this function for bugs and suggest improvements", "CODE_REVIEW"),
    ("My app crashes with a KeyError when I access the config dict", "DEBUGGING"),
    ("Write a docstring for this class explaining its public API", "DOCUMENTATION"),
    ("What's the difference between REST and GraphQL?", "GENERAL_QUESTION"),
]

# Chain-of-thought examples with reasoning traces
COT_EXAMPLES = [
    (
        "Write a Python function that sorts a list using merge sort",
        "The user is asking me to CREATE new code (a sorting function). They're not reviewing "
        "existing code or fixing a bug — they want something written from scratch. "
        "Category: CODE_GENERATION",
    ),
    (
        "My app crashes with a KeyError when I access the config dict",
        "The user has existing code that is FAILING — they mention a specific error (KeyError) "
        "and a runtime crash. This is about finding and fixing an existing problem, not writing "
        "new code or reviewing for quality. Category: DEBUGGING",
    ),
    (
        "What's the difference between REST and GraphQL?",
        "The user is asking a conceptual question about technology. They don't have code to "
        "write, review, or debug — they want an explanation of concepts. "
        "Category: GENERAL_QUESTION",
    ),
]

# Test inputs to classify with all four methods
TEST_INPUTS = [
    "Create a REST API endpoint that handles user registration",
    "Why does this recursive function cause a stack overflow?",
    "Look at my authentication middleware and tell me if it's secure",
    "Generate API reference docs for these three modules",
    "How does garbage collection work in Python?",
]


class FewShotClient:
    """Demonstrates few-shot and chain-of-thought prompting techniques."""

    def __init__(self, model: str, token_tracker: AnthropicTokenTracker):
        self.client = anthropic.Anthropic()
        self.model = model
        self.token_tracker = token_tracker

    def _call(self, system_prompt: str, user_content: str) -> str:
        """Make a single API call and track tokens."""
        response = self.client.messages.create(
            model=self.model,
            temperature=0.0,
            max_tokens=256,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )
        self.token_tracker.track(response.usage)
        return str(response.content[0].text).strip()

    def classify_zero_shot(self, request: str) -> str:
        """Classify with no examples — baseline approach."""
        system = (
            f"Classify the following request into exactly one category: {CATEGORIES}\n"
            "Respond with ONLY the category name, nothing else."
        )
        return self._call(system, request)

    def classify_few_shot(self, request: str) -> str:
        """Classify with examples provided for in-context learning."""
        # Build few-shot examples into the prompt
        examples = "\n".join(
            f'Request: "{req}"\nCategory: {cat}' for req, cat in CLASSIFICATION_EXAMPLES
        )
        system = (
            f"Classify requests into exactly one category: {CATEGORIES}\n\n"
            "Here are examples:\n\n"
            f"{examples}\n\n"
            "Respond with ONLY the category name, nothing else."
        )
        return self._call(system, f'Request: "{request}"\nCategory:')

    def classify_cot(self, request: str) -> str:
        """Classify with chain-of-thought reasoning before the answer."""
        system = (
            f"Classify requests into exactly one category: {CATEGORIES}\n\n"
            "Think step by step:\n"
            "1. What is the user trying to accomplish?\n"
            "2. Are they creating, reviewing, fixing, documenting, or asking?\n"
            "3. Based on your reasoning, state the category.\n\n"
            "End your response with a line: Category: <CATEGORY_NAME>"
        )
        return self._call(system, request)

    def classify_few_shot_cot(self, request: str) -> str:
        """Classify with both examples and reasoning traces — the strongest approach."""
        examples = "\n\n".join(
            f'Request: "{req}"\nReasoning: {reasoning}' for req, reasoning in COT_EXAMPLES
        )
        system = (
            f"Classify requests into exactly one category: {CATEGORIES}\n\n"
            "For each request, reason step by step about what the user wants, "
            "then state the category.\n\n"
            f"Examples:\n\n{examples}\n\n"
            "End your response with a line: Category: <CATEGORY_NAME>"
        )
        return self._call(system, f'Request: "{request}"')


def _extract_category(response: str) -> str:
    """Extract the category label from a response that may contain reasoning."""
    # Check for "Category: X" pattern first
    for line in reversed(response.strip().splitlines()):
        if line.strip().startswith("Category:"):
            return line.strip().split("Category:")[-1].strip()
    # Fall back to the full response (zero-shot / few-shot return just the label)
    return response.strip().split("\n")[-1].strip()


def main() -> None:
    """Run all test inputs through four classification methods and compare results."""
    console = Console()
    token_tracker = AnthropicTokenTracker()
    client = FewShotClient("claude-sonnet-4-20250514", token_tracker)

    console.print(
        Panel(
            "[bold cyan]Few-Shot & Chain-of-Thought Prompting[/bold cyan]\n\n"
            "Comparing 4 prompting strategies for agent request classification.\n"
            "Each test input is classified by all methods for side-by-side comparison.",
            title="Prompt Engineering — Anthropic",
        )
    )

    methods = {
        "Zero-Shot": client.classify_zero_shot,
        "Few-Shot": client.classify_few_shot,
        "CoT": client.classify_cot,
        "Few-Shot+CoT": client.classify_few_shot_cot,
    }

    # Build comparison table
    table = Table(title="Classification Results", show_lines=True)
    table.add_column("Test Input", style="cyan", max_width=45)
    for method_name in methods:
        table.add_column(method_name, style="green", max_width=20)

    for test_input in TEST_INPUTS:
        logger.info("Classifying: %s", test_input[:60])
        results = []
        for method_name, method in methods.items():
            try:
                raw = method(test_input)
                results.append(_extract_category(raw))
            except Exception as e:
                logger.error("Error in %s: %s", method_name, e)
                results.append("ERROR")
        table.add_row(test_input[:45], *results)

    console.print()
    console.print(table)

    # Token usage comparison
    console.print(
        "\n[dim]Note: Few-shot methods use more input tokens due to examples in the prompt. "
        "CoT methods use more output tokens due to reasoning traces.[/dim]"
    )
    console.print()
    token_tracker.report()


if __name__ == "__main__":
    main()
