"""Pydantic data models for the eval harness pipeline."""

from pydantic import BaseModel, Field


class EvalTask(BaseModel):
    """A single evaluation task from the golden dataset."""

    id: str
    question: str
    expected_keywords: list[str] = Field(default_factory=list)
    expected_source_ids: list[str] = Field(default_factory=list)
    difficulty: str = "medium"
    category: str = "general"


class TraceSpan(BaseModel):
    """A single span in an execution trace."""

    name: str
    span_type: str
    start_time: float
    end_time: float = 0.0
    tokens: dict[str, int] = Field(default_factory=dict)
    children: list["TraceSpan"] = Field(default_factory=list)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        """Duration in milliseconds."""
        return (self.end_time - self.start_time) * 1000 if self.end_time else 0.0


class GraderScore(BaseModel):
    """Score from a single grader."""

    grader_name: str
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class EvalTrial(BaseModel):
    """One execution of the agent on a task."""

    task_id: str
    trial_number: int = 1
    answer: str = ""
    tool_calls: list[dict] = Field(default_factory=list)
    trace: list[TraceSpan] = Field(default_factory=list)
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


class EvalResult(BaseModel):
    """Aggregated result for one task."""

    task_id: str
    trials: list[EvalTrial] = Field(default_factory=list)
    grader_scores: list[GraderScore] = Field(default_factory=list)
    pass_rate: float = 0.0
    avg_score: float = 0.0


class SafetyResult(BaseModel):
    """Result from a safety/red-team test."""

    attack_id: str
    attack_name: str
    category: str
    blocked: bool
    severity: str = "medium"
    details: str = ""


class BenchmarkEntry(BaseModel):
    """A single benchmark measurement."""

    config_name: str
    task_id: str
    accuracy: float = 0.0
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    tokens: int = 0


class EvalReport(BaseModel):
    """Complete evaluation report."""

    agent_name: str = "Research Assistant"
    eval_results: list[EvalResult] = Field(default_factory=list)
    safety_results: list[SafetyResult] = Field(default_factory=list)
    benchmark_entries: list[BenchmarkEntry] = Field(default_factory=list)
    overall_pass_rate: float = 0.0
    overall_safety_score: float = 0.0
    total_cost_usd: float = 0.0
    total_latency_ms: float = 0.0
