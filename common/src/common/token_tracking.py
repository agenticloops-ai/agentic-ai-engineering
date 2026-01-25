"""
Token usage tracking utilities for LLM API calls.

Provides a unified interface with provider-specific implementations for
tracking token usage across different LLM providers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class TokenUsageTracker(ABC):
    """
    Abstract base class for tracking token usage across API calls.

    Provides a common interface for different LLM providers while allowing
    provider-specific token extraction logic.
    """

    def __init__(self):
        """Initialize the token tracker."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    @abstractmethod
    def track(self, usage: Any) -> None:
        """
        Track tokens from a response's usage data.

        Args:
            usage: Usage object from LLM response (format varies by provider)
        """
        pass

    def report(self) -> None:
        """Log the total token usage."""
        total = self.total_input_tokens + self.total_output_tokens
        logger.info(
            "Token Usage - Input: %d, Output: %d, Total: %d",
            self.total_input_tokens,
            self.total_output_tokens,
            total,
        )

    def get_total_tokens(self) -> int:
        """Get the total number of tokens used."""
        return self.total_input_tokens + self.total_output_tokens

    def get_input_tokens(self) -> int:
        """Get the total input tokens used."""
        return self.total_input_tokens

    def get_output_tokens(self) -> int:
        """Get the total output tokens used."""
        return self.total_output_tokens

    def reset(self) -> None:
        """Reset all token counts to zero."""
        self.total_input_tokens = 0
        self.total_output_tokens = 0


class AnthropicTokenTracker(TokenUsageTracker):
    """
    Token tracker for Anthropic Claude API.

    Handles Anthropic's usage format with input_tokens and output_tokens.
    """

    def track(self, usage: Any) -> None:
        """
        Track tokens from an Anthropic response.

        Args:
            usage: Anthropic usage object with input_tokens and output_tokens
        """
        if hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens
        else:
            logger.warning(
                "Invalid Anthropic usage format: %s. Expected input_tokens and output_tokens.",
                type(usage),
            )


class OpenAITokenTracker(TokenUsageTracker):
    """
    Token tracker for OpenAI API.

    Handles both OpenAI API formats:
    - Responses API: input_tokens, output_tokens
    - Chat Completions API: prompt_tokens, completion_tokens
    """

    def track(self, usage: Any) -> None:
        """
        Track tokens from an OpenAI response.

        Args:
            usage: OpenAI usage object (supports both API formats)
        """
        # Responses API format
        if hasattr(usage, "input_tokens") and hasattr(usage, "output_tokens"):
            self.total_input_tokens += usage.input_tokens
            self.total_output_tokens += usage.output_tokens
        # Chat Completions API format
        elif hasattr(usage, "prompt_tokens") and hasattr(usage, "completion_tokens"):
            self.total_input_tokens += usage.prompt_tokens
            self.total_output_tokens += usage.completion_tokens
        else:
            logger.warning(
                "Invalid OpenAI usage format: %s. Expected input_tokens/output_tokens or prompt_tokens/completion_tokens.",
                type(usage),
            )


class LiteLLMTokenTracker(TokenUsageTracker):
    """
    Token tracker for LiteLLM.

    Handles LiteLLM's normalized usage format with prompt_tokens and completion_tokens.
    """

    def track(self, usage: Any) -> None:
        """
        Track tokens from a LiteLLM response.

        Args:
            usage: LiteLLM usage object with prompt_tokens and completion_tokens
        """
        if hasattr(usage, "prompt_tokens") and hasattr(usage, "completion_tokens"):
            self.total_input_tokens += usage.prompt_tokens
            self.total_output_tokens += usage.completion_tokens
        else:
            logger.warning(
                "Invalid LiteLLM usage format: %s. Expected prompt_tokens and completion_tokens.",
                type(usage),
            )
