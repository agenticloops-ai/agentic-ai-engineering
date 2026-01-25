"""
Shared logging configuration for AI agent lessons.

Provides consistent Rich-based logging setup across all lessons.
"""

import logging

from rich.logging import RichHandler


def setup_logging(name: str = __name__, level: int = logging.INFO) -> logging.Logger:
    """
    Configure logging with Rich handler and return a logger.

    Args:
        name: Logger name (typically __name__)
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    # Configure logging with Rich
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                show_time=False,
                show_path=False,
                markup=True,
            )
        ],
        force=True,  # Override any existing config
    )

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Return logger for the calling module
    return logging.getLogger(name)
