"""
Simple LLM Call (OpenAI)

Demonstrates a basic call to the OpenAI API.
Shows separation of agent logic from orchestration.
"""

from common.logging_config import setup_logging
from dotenv import find_dotenv, load_dotenv
from openai import OpenAI

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)


class LLMClient:
    """
    Simple agent that makes basic LLM calls to OpenAI.

    Encapsulates all agent logic including API interaction.
    """

    def __init__(self, model: str):
        """
        Initialize the agent.

        Args:
            model: OpenAI model name
        """
        self.client = OpenAI()
        self.model = model
        self.system_prompt = "You are a helpful AI assistant. Provide clear and concise answers."

    def run(self, prompt: str) -> str:
        """
        Execute the agent with a given prompt.
        """
        logger.info(f"Calling model: {self.model}")

        response = self.client.responses.create(
            model=self.model,
            temperature=0.1,
            max_output_tokens=1024,
            instructions=self.system_prompt,
            input=prompt,
        )

        # Log token usage if available
        if hasattr(response, "usage") and response.usage:
            logger.info(
                f"Token usage - Input: {response.usage.input_tokens}, "
                f"Output: {response.usage.output_tokens}, "
                f"Total: {response.usage.total_tokens}"
            )

        # Extract and return response
        return response.output_text or ""


def main() -> None:
    """
    Main orchestration function.

    Sets up the agent and coordinates execution flow.
    """

    agent = LLMClient("gpt-4o")

    prompt = "Explain what an AI agent is in 2-3 sentences."
    logger.info(f"👤 User: {prompt}")

    # Call LLM
    response = agent.run(prompt)

    # Display results
    logger.info(f"🤖 Response: {response}")


if __name__ == "__main__":
    main()
