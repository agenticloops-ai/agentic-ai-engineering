"""
Simple LLM Call (Google Gemini)

Demonstrates a basic call to the Google Vertex AI API.
Shows separation of agent logic from orchestration.
"""

from google import genai
from google.genai import types
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
        self.client = genai.Client()
        self.model = model
        self.system_prompt = "You are a helpful AI assistant. Provide clear and concise answers."

    def run(self, prompt: str) -> str:
        """
        Execute the agent with a given prompt.
        """
        logger.info(f"Calling model: {self.model}")

        # Make the API call
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level="low"),
                system_instruction=self.system_prompt,
                safety_settings=[
                    types.SafetySetting(
                        category='HARM_CATEGORY_HATE_SPEECH',
                        threshold='BLOCK_ONLY_HIGH',
                    )
                ]
            ),
        )

        # Log token usage
        logger.info(
            f"Token usage - Input: {response.usage_metadata.prompt_token_count}, "
            f"Output: {response.usage_metadata.candidates_token_count}, "
            f"Total: {response.usage_metadata.total_token_count}"
        )

        # Extract and return response
        result = response.text
        return str(result)


def main() -> None:
    """
    Main orchestration function.

    Sets up the agent and coordinates execution flow.
    """

    # Initialize agent
    agent = LLMClient("gemini-3-flash-preview")

    prompt = "Explain what an AI agent is in 2-3 sentences."
    logger.info(f"👤 User: {prompt}")

    # Call LLM
    response = agent.run(prompt)

    # Display results
    logger.info(f"🤖 Response: {response}")


if __name__ == "__main__":
    main()
