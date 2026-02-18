"""
Pydantic models for pipeline data and typed event system.

Data models validate LLM structured output. Event models enable type-safe progress
tracking via async generator — the entry point uses pattern matching to render each
event type with appropriate Rich UI.
"""

from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field, computed_field


# ─── Data Models ─────────────────────────────────────────────────────────────


class ContentType(str, Enum):
    """Content types the pipeline can produce."""

    BLOG = "blog"
    TUTORIAL = "tutorial"
    CONCEPT = "concept"


class ClassificationResult(BaseModel):
    """Routing output: content type + topic analysis."""

    content_type: ContentType
    topic: str
    key_aspects: list[str]
    reasoning: str


class Source(BaseModel):
    """A web source discovered during research or refinement."""

    title: str
    url: str


class Subtopic(BaseModel):
    """Research plan entry: one subtopic to investigate."""

    title: str
    research_prompt: str


class ResearchSection(BaseModel):
    """Research output: one section of synthesized findings."""

    title: str
    content: str
    sources: list[Source] = []


class EvaluationResult(BaseModel):
    """5-dimension quality assessment of a draft."""

    clarity: int = Field(ge=1, le=10)
    technical_accuracy: int = Field(ge=1, le=10)
    structure: int = Field(ge=1, le=10)
    engagement: int = Field(ge=1, le=10)
    human_voice: int = Field(ge=1, le=10)
    issues: list[str] = []
    suggestions: list[str] = []

    @computed_field  # type: ignore[prop-decorator]
    @property
    def avg_score(self) -> float:
        """Average across all five dimensions."""
        return (
            self.clarity
            + self.technical_accuracy
            + self.structure
            + self.engagement
            + self.human_voice
        ) / 5


class SocialContent(BaseModel):
    """Fan-out output: social media content for three platforms."""

    linkedin: str = ""
    twitter: str = ""
    newsletter: str = ""


class SeoResult(BaseModel):
    """Voting output: best SEO title from candidates."""

    winning_title: str
    reasoning: str
    candidates: list[str] = []


class WritingResult(BaseModel):
    """Final pipeline output: article + optional promo pack."""

    content_type: ContentType
    title: str
    content: str
    final_score: float
    iterations: int
    sources: list[Source] = []
    social: SocialContent | None = None
    seo: SeoResult | None = None


# ─── Typed Events ────────────────────────────────────────────────────────────
# Each event is a Pydantic model with a Literal stage field.
# The async generator yields these; the entry point uses match/case to render.


class ClassifyStartEvent(BaseModel):
    """Emitted when classification begins."""

    stage: Literal["classify_start"] = "classify_start"


class ClassifyDoneEvent(BaseModel):
    """Emitted when classification completes."""

    stage: Literal["classify_done"] = "classify_done"
    classification: ClassificationResult


class HumanCheckpointEvent(BaseModel):
    """Emitted when the agent needs human input."""

    stage: Literal["human_checkpoint"] = "human_checkpoint"
    checkpoint_id: str
    title: str
    content: str
    question: str


class PlanStartEvent(BaseModel):
    """Emitted when research planning begins."""

    stage: Literal["plan_start"] = "plan_start"


class PlanDoneEvent(BaseModel):
    """Emitted when research planning completes."""

    stage: Literal["plan_done"] = "plan_done"
    subtopics: list[Subtopic]


class ResearchStartEvent(BaseModel):
    """Emitted when parallel research begins."""

    stage: Literal["research_start"] = "research_start"
    count: int


class ResearchSectionDoneEvent(BaseModel):
    """Emitted when one research worker completes."""

    stage: Literal["research_section_done"] = "research_section_done"
    title: str
    sources: list[Source] = []


class ResearchDoneEvent(BaseModel):
    """Emitted when all research workers complete."""

    stage: Literal["research_done"] = "research_done"
    sections: list[ResearchSection]


class WriteStartEvent(BaseModel):
    """Emitted when writing begins."""

    stage: Literal["write_start"] = "write_start"
    iteration: int


class WriteDoneEvent(BaseModel):
    """Emitted when writing completes."""

    stage: Literal["write_done"] = "write_done"
    iteration: int
    content_length: int
    content: str
    sources: list[Source] = []


class EvaluateStartEvent(BaseModel):
    """Emitted when evaluation begins."""

    stage: Literal["evaluate_start"] = "evaluate_start"
    iteration: int


class EvaluateDoneEvent(BaseModel):
    """Emitted when evaluation completes."""

    stage: Literal["evaluate_done"] = "evaluate_done"
    iteration: int
    evaluation: EvaluationResult


class RefineStartEvent(BaseModel):
    """Emitted when refinement rewrite begins."""

    stage: Literal["refine_start"] = "refine_start"
    iteration: int


class SocialStartEvent(BaseModel):
    """Emitted when social media fan-out begins."""

    stage: Literal["social_start"] = "social_start"


class SocialWriterDoneEvent(BaseModel):
    """Emitted when one social media writer completes."""

    stage: Literal["social_writer_done"] = "social_writer_done"
    name: str


class SocialDoneEvent(BaseModel):
    """Emitted when all social media writers complete."""

    stage: Literal["social_done"] = "social_done"
    social: SocialContent


class SeoStartEvent(BaseModel):
    """Emitted when SEO title voting begins."""

    stage: Literal["seo_start"] = "seo_start"


class SeoCandidateEvent(BaseModel):
    """Emitted when one SEO title candidate is generated."""

    stage: Literal["seo_candidate"] = "seo_candidate"
    title: str


class SeoDoneEvent(BaseModel):
    """Emitted when SEO title voting completes."""

    stage: Literal["seo_done"] = "seo_done"
    seo: SeoResult


class CompleteEvent(BaseModel):
    """Emitted when the full pipeline completes."""

    stage: Literal["complete"] = "complete"
    result: WritingResult


AgentEvent = Union[
    ClassifyStartEvent,
    ClassifyDoneEvent,
    HumanCheckpointEvent,
    PlanStartEvent,
    PlanDoneEvent,
    ResearchStartEvent,
    ResearchSectionDoneEvent,
    ResearchDoneEvent,
    WriteStartEvent,
    WriteDoneEvent,
    EvaluateStartEvent,
    EvaluateDoneEvent,
    RefineStartEvent,
    SocialStartEvent,
    SocialWriterDoneEvent,
    SocialDoneEvent,
    SeoStartEvent,
    SeoCandidateEvent,
    SeoDoneEvent,
    CompleteEvent,
]
