"""
Simple LLM Call (LiteLLM)

Demonstrates a basic call using LiteLLM, which provides a unified interface
for multiple LLM providers (OpenAI, Anthropic, Google, etc.).
Shows separation of agent logic from orchestration.
"""

from common.logging_config import setup_logging
from dotenv import find_dotenv, load_dotenv
from litellm import completion

# Load environment variables from root .env file
load_dotenv(find_dotenv())

# Configure logging
logger = setup_logging(__name__)


class LLMClient:
    """
    Simple client that makes basic LLM calls using LiteLLM.

    LiteLLM provides a unified interface across different providers,
    allowing easy switching between models without code changes.
    """

    def __init__(self, model: str):
        """
        Initialize the client.
        """
        self.model = model
        self.system_prompt = "You are a helpful AI assistant. Provide clear and concise answers."

    def run(self, prompt: str) -> str:
        """
        Execute the client with a given prompt.
        """
        logger.info(f"Calling model: {self.model}")

        # Make the API call
        response = completion(
            model=self.model,
            temperature=0.1,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        # Log token usage
        if hasattr(response, "usage") and response.usage:
            logger.info(
                f"Token usage - Input: {response.usage.prompt_tokens}, "
                f"Output: {response.usage.completion_tokens}, "
                f"Total: {response.usage.total_tokens}"
            )

        # Extract and return response
        result = response.choices[0].message.content
        return str(result)


def main() -> None:
    """
    Main orchestration function.

    Sets up the client and coordinates execution flow.
    """

    # You can easily switch between providers by changing the model string:
    # - "gpt-4o" for OpenAI
    # - "claude-3-5-sonnet-20241022" for Anthropic
    # - "gemini/gemini-pro" for Google
    agent = LLMClient("gpt-4o")

    prompt = "Explain what an AI agent is in 2-3 sentences."
    logger.info(f"👤 User: {prompt}")

    # Call LLM
    response = agent.run(prompt)

    # Display results
    logger.info(f"🤖 Response: {response}")


if __name__ == "__main__":
    main()
