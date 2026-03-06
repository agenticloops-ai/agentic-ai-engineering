"""
Shared data classes and model configurations for benchmark scripts.

Defines ModelConfig, BenchmarkResult, BenchmarkConfig, and default model configs.
"""

from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Configuration for a model to benchmark."""

    name: str
    provider: str  # "anthropic" or "openai"
    model_id: str
    cost_per_input_token: float  # dollars per 1M tokens
    cost_per_output_token: float  # dollars per 1M tokens


@dataclass
class BenchmarkResult:
    """Result from running one benchmark task."""

    task_id: str
    config_name: str
    answer: str
    keyword_score: float  # 0.0-1.0 based on expected keywords found
    latency_ms: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_calls: int


@dataclass
class BenchmarkConfig:
    """A single benchmark configuration (model + prompt combination)."""

    name: str
    model: ModelConfig
    prompt_strategy: str
    system_prompt: str


# Default model configurations
MODEL_CONFIGS = [
    ModelConfig("Claude Sonnet", "anthropic", "claude-sonnet-4-5-20250929", 3.0, 15.0),
    ModelConfig("Claude Haiku", "anthropic", "claude-haiku-4-5-20251001", 0.80, 4.0),
    ModelConfig("GPT-4.1 mini", "openai", "gpt-4.1-mini", 0.40, 1.60),
]
