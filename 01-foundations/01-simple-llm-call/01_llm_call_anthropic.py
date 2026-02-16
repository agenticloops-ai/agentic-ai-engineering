"""
Simple LLM Call (Anthropic)

Demonstrates a basic call to the Anthropic Claude API.
Shows separation of agent logic from orchestration.
"""

import anthropic
from dotenv import find_dotenv, load_dotenv

from common.logging_config import setup_logging

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)


class LLMClient:
    """
    Simple agent that makes basic LLM calls to Claude.

    Encapsulates all agent logic including API interaction.
    """

    def __init__(self, model: str):
        """
        Initialize the agent.
        """
        self.client = anthropic.Anthropic()
        self.model = model
        self.system_prompt = "You are a helpful AI assistant. Provide clear and concise answers."

    def run(self, prompt: str) -> str:
        """
        Execute the agent with a given prompt.
        """
        logger.info(f"Calling model: {self.model}")

        # Make the API call
        response = self.client.messages.create(
            model=self.model,
            temperature=0.1,
            max_tokens=1024,
            system=self.system_prompt,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        # Log token usage
        logger.info(
            f"Token usage - Input: {response.usage.input_tokens}, "
            f"Output: {response.usage.output_tokens}, "
            f"Total: {response.usage.input_tokens + response.usage.output_tokens}"
        )

        # Extract and return response
        result = response.content[0].text
        return str(result)


def main() -> None:
    """
    Main orchestration function.

    Sets up the agent and coordinates execution flow.
    """

    # Initialize agent
    agent = LLMClient("claude-sonnet-4-5-20250929")

    prompt = "Explain what an AI agent is in 2-3 sentences."
    logger.info(f"👤 User: {prompt}")

    # Call LLM
    response = agent.run(prompt)

    # Display results
    logger.info(f"🤖 Response: {response}")


if __name__ == "__main__":
    main()
