"""
Content writer agent composing all patterns from tutorials 02-07.

Pipeline phases map to patterns:
- _classify()             → routing (03)
- _plan() / _replan()     → orchestrator (05)
- _research_parallel()    → parallel workers (05) with web search
- _write()                → prompt chaining (02) with type-specific voice
- _evaluate()             → evaluator-optimizer (06)
- _write_social()         → parallelization fan-out (04)
- _generate_seo()         → parallelization voting (04)

Human-in-the-loop (07) checkpoints are yielded as HumanCheckpointEvent and handled
by the entry point via on_human_checkpoint callback.

Async generator (run_stream) yields typed events so the UI layer can render progress
without any coupling to the agent logic.
"""

import asyncio
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, AsyncGenerator, cast

import anthropic
from anthropic import RateLimitError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from common import AnthropicTokenTracker, setup_logging

from . import prompts
from .models import (
    ClassificationResult,
    ClassifyDoneEvent,
    ClassifyStartEvent,
    CompleteEvent,
    ContentType,
    EvaluateDoneEvent,
    EvaluateStartEvent,
    EvaluationResult,
    HumanCheckpointEvent,
    PlanDoneEvent,
    PlanStartEvent,
    RefineStartEvent,
    ResearchDoneEvent,
    ResearchSection,
    ResearchSectionDoneEvent,
    ResearchStartEvent,
    SeoCandidateEvent,
    SeoDoneEvent,
    SeoResult,
    SeoStartEvent,
    SocialContent,
    SocialDoneEvent,
    SocialStartEvent,
    SocialWriterDoneEvent,
    Source,
    Subtopic,
    WriteDoneEvent,
    WriteStartEvent,
    WritingResult,
)
from .models import AgentEvent  # noqa: F401 — re-export for type hints
from .tools import (
    CLASSIFY_TOOLS,
    EVALUATION_TOOLS,
    PLANNING_TOOLS,
    SEO_EVALUATION_TOOLS,
    WEB_SEARCH_TOOL,
    ToolExecutor,
)

logger = setup_logging(__name__)

# Human checkpoint callback type
HumanCheckpointFn = Callable[[HumanCheckpointEvent], tuple[bool, str]]


class ContentWriterAgent:
    """Full content creation agent composing all patterns from tutorials 02-07."""

    def __init__(
        self,
        model: str,
        research_model: str,
        token_tracker: AnthropicTokenTracker,
    ) -> None:
        # Disable SDK's built-in retry — tenacity handles it with longer backoff
        self.client = anthropic.Anthropic(max_retries=0)
        self.model = model
        self.research_model = research_model
        self.token_tracker = token_tracker
        self.tool_executor = ToolExecutor()

    # ─── LLM call primitives ──────────────────────────────────────────────

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential(multiplier=2, min=30, max=120),
        stop=stop_after_attempt(6),
        before_sleep=before_sleep_log(logger, log_level=20),
    )
    def _call_api(self, **kwargs: Any) -> Any:
        """Low-level API call with retry on rate limits."""
        return self.client.messages.create(**kwargs)

    def _call_llm(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        use_light: bool = True,
        max_tokens: int = 4096,
        temperature: float = 1.0,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, str] | None = None,
    ) -> anthropic.types.Message:
        """Single LLM call with token tracking."""
        model = self.research_model if use_light else self.model
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        tool_names = [t.get("name", t.get("type", "unknown")) for t in tools or []]
        logger.info("Calling %s, tools=%s", model, tool_names)

        response = self._call_api(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
            **kwargs,
        )
        self.token_tracker.track(response.usage)
        return response

    def _call_tool(self, system: str, user_message: str, tools: list, tool_name: str) -> dict:
        """LLM call that returns structured output via tool_choice."""
        response = self._call_llm(
            system,
            [{"role": "user", "content": user_message}],
            use_light=False,
            max_tokens=1024,
            tools=tools,
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if block.type == "tool_use":
                return cast(dict[Any, Any], block.input)
        raise ValueError(f"No tool call in response for {tool_name}")

    def _run_agent_loop(
        self,
        system: str,
        user_message: str,
        *,
        tools: list[dict[str, Any]],
        use_light: bool = True,
        max_tokens: int = 4096,
        max_turns: int = 5,
    ) -> tuple[str, list[Source]]:
        """Agentic loop — runs LLM with tools across multiple turns."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]
        sources: list[Source] = []

        response = None
        for turn in range(max_turns):
            response = self._call_llm(
                system,
                messages,
                use_light=use_light,
                max_tokens=max_tokens,
                tools=tools,
            )

            # Collect sources from web_search_tool_result blocks
            for block in response.content:
                if block.type == "web_search_tool_result" and isinstance(block.content, list):
                    for result in block.content:
                        sources.append(Source(title=result.title, url=result.url))

            if response.stop_reason == "end_turn":
                text_parts = [b.text for b in response.content if b.type == "text"]
                return "\n\n".join(text_parts), sources

            # Tool was used — execute and feed results back
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("  tool %s invoked (turn %d)", block.name, turn + 1)
                    result = self.tool_executor.execute(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
            else:
                break

        if response is None:
            return "", sources
        text_parts = [b.text for b in response.content if b.type == "text"]
        return "\n\n".join(text_parts), sources

    def _call_text(
        self,
        system: str,
        user_message: str,
        *,
        use_light: bool = True,
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> str:
        """Single-turn LLM call without tools."""
        response = self._call_llm(
            system,
            [{"role": "user", "content": user_message}],
            use_light=use_light,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text_parts = [b.text for b in response.content if b.type == "text"]
        return "\n\n".join(text_parts)

    # ─── Pipeline phases ─────────────────────────────────────────────────

    def _classify(self, topic: str) -> ClassificationResult:
        """Classify topic into content type with structured output (routing pattern)."""
        logger.info("Phase: classify — %s", topic[:50])
        data = self._call_tool(
            prompts.CLASSIFICATION_SYSTEM, topic, CLASSIFY_TOOLS, "classify_content"
        )
        return ClassificationResult(**data)

    def _plan(
        self, topic: str, content_type: ContentType, key_aspects: list[str]
    ) -> list[Subtopic]:
        """Create a research plan with 2-4 subtopics (orchestrator pattern)."""
        logger.info("Phase: plan — %s (%s)", topic[:50], content_type.value)
        aspects_text = ", ".join(key_aspects) if key_aspects else "general overview"
        result = self._call_tool(
            f"You are a research planner for a {content_type.value} article. "
            f"Key aspects to cover: {aspects_text}. "
            "Break the topic into 2-3 focused subtopics that can be researched "
            "independently. Each should cover a distinct angle.",
            f"Plan research for: {topic}",
            PLANNING_TOOLS,
            "create_research_plan",
        )
        return [Subtopic(**s) for s in result["subtopics"]]

    def _replan(self, topic: str, plan_text: str, feedback: str) -> list[Subtopic]:
        """Revise a research plan based on human feedback."""
        logger.info("Phase: replan")
        result = self._call_tool(
            f"Revise this research plan based on feedback: {feedback}",
            f"Original plan:\n{plan_text}\n\nTopic: {topic}",
            PLANNING_TOOLS,
            "create_research_plan",
        )
        return [Subtopic(**s) for s in result["subtopics"]]

    def _research_section(self, subtopic: Subtopic) -> ResearchSection:
        """Research one subtopic using web search (worker pattern)."""
        logger.info("Phase: research — %s", subtopic.title)
        content, sources = self._run_agent_loop(
            prompts.RESEARCH_SYSTEM,
            subtopic.research_prompt,
            tools=[WEB_SEARCH_TOOL],
            max_tokens=1024,
        )
        return ResearchSection(title=subtopic.title, content=content, sources=sources)

    def _write(
        self,
        topic: str,
        sections: list[ResearchSection],
        content_type: ContentType,
        feedback: str | None = None,
        previous_draft: str | None = None,
    ) -> tuple[str, list[Source]]:
        """Write or revise the article with type-specific voice (chaining pattern)."""
        logger.info("Phase: write — %s (%s)", topic[:50], content_type.value)

        research_text = "\n\n".join(f"## {s.title}\n{s.content}" for s in sections)

        if feedback and previous_draft:
            # Revision: Sonnet with web search for additional concepts
            user_msg = (
                f"Topic: {topic}\n\n"
                f"Research:\n{research_text}\n\n"
                f"Feedback to address:\n{feedback}\n\n"
                f"Previous draft:\n{previous_draft}\n\n"
                "Revise the draft to address all feedback."
            )
            return self._run_agent_loop(
                prompts.get_revision_system(content_type),
                user_msg,
                tools=[WEB_SEARCH_TOOL],
                use_light=False,
                max_tokens=8192,
            )
        else:
            # Initial write: Sonnet for quality structure and completeness
            user_msg = (
                f"Research:\n{research_text}\n\n"
                f"Write a complete {content_type.value} about: {topic}"
            )
            content = self._call_text(
                prompts.get_writing_system(content_type),
                user_msg,
                use_light=False,
                max_tokens=8192,
            )
            return content, []

    def _evaluate(self, topic: str, draft: str) -> EvaluationResult:
        """Evaluate draft with 5-dimension structured scoring (evaluator pattern)."""
        logger.info("Phase: evaluate")
        data = self._call_tool(
            prompts.EVALUATION_SYSTEM,
            f"Topic: {topic}\n\nDraft to evaluate:\n\n{draft}",
            EVALUATION_TOOLS,
            "evaluate_draft",
        )
        return EvaluationResult(**data)

    # ─── Social media (parallelization fan-out from 04) ──────────────────

    def _write_linkedin(self, article: str) -> str:
        """Generate a LinkedIn professional summary."""
        return self._call_text(
            prompts.LINKEDIN_SYSTEM,
            f"Create a LinkedIn post from this article:\n\n{article[:2000]}",
            max_tokens=2048,
        )

    def _write_twitter(self, article: str) -> str:
        """Generate a Twitter/X thread of 5 tweets."""
        return self._call_text(
            prompts.TWITTER_SYSTEM,
            f"Create a tweet thread from this article:\n\n{article[:2000]}",
            max_tokens=2048,
        )

    def _write_newsletter(self, article: str) -> str:
        """Generate a newsletter subject line and intro paragraph."""
        return self._call_text(
            prompts.NEWSLETTER_SYSTEM,
            f"Create a newsletter intro from this article:\n\n{article[:2000]}",
            max_tokens=2048,
        )

    def _write_social(self, article: str) -> SocialContent:
        """Generate social media content in parallel (fan-out pattern)."""
        logger.info("Phase: social media fan-out")
        results: dict[str, str] = {}
        writers = {
            "linkedin": self._write_linkedin,
            "twitter": self._write_twitter,
            "newsletter": self._write_newsletter,
        }
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(fn, article): name for name, fn in writers.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    logger.error("Social writer %s failed: %s", name, e)
                    results[name] = f"Error: {e}"
        return SocialContent(**results)

    # ─── SEO title (parallelization voting from 04) ──────────────────────

    def _generate_seo_title(self, article: str, temperature: float) -> str:
        """Generate a single SEO title candidate at a given temperature."""
        return self._call_text(
            prompts.SEO_TITLE_SYSTEM,
            f"Generate an SEO title for:\n\n{article[:500]}",
            max_tokens=128,
            temperature=temperature,
        )

    def _vote_best_title(self, titles: list[str], article: str) -> dict:
        """Use structured output to pick the best SEO title (voting pattern)."""
        titles_text = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
        return self._call_tool(
            prompts.SEO_EVALUATOR_SYSTEM,
            f"Article summary: {article[:300]}\n\nCandidate titles:\n{titles_text}",
            SEO_EVALUATION_TOOLS,
            "pick_best_title",
        )

    def _generate_seo(self, article: str) -> SeoResult:
        """Generate SEO title via voting pattern: 3 candidates → evaluator picks best."""
        logger.info("Phase: SEO title voting")
        temperatures = [0.3, 0.7, 1.0]
        titles: list[str] = []

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures_list = [
                executor.submit(self._generate_seo_title, article, temp) for temp in temperatures
            ]
            for future in as_completed(futures_list):
                try:
                    titles.append(future.result().strip())
                except Exception as e:
                    logger.error("SEO title generation failed: %s", e)

        if not titles:
            return SeoResult(winning_title="", reasoning="All candidates failed", candidates=[])

        result = self._vote_best_title(titles, article)
        return SeoResult(
            winning_title=result["winning_title"],
            reasoning=result["reasoning"],
            candidates=titles,
        )

    # ─── Async event stream ──────────────────────────────────────────────

    async def run_stream(
        self,
        topic: str,
        *,
        score_threshold: float = 7.0,
        max_refinements: int = 2,
        on_human_checkpoint: HumanCheckpointFn | None = None,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Async generator yielding typed events as the pipeline progresses."""
        logger.info("Pipeline start — topic=%s, threshold=%.1f", topic[:50], score_threshold)

        def _checkpoint(
            checkpoint_id: str, title: str, content: str, question: str
        ) -> tuple[bool, str]:
            """Call the human checkpoint callback if provided."""
            if on_human_checkpoint is None:
                return True, ""
            event = HumanCheckpointEvent(
                checkpoint_id=checkpoint_id,
                title=title,
                content=content,
                question=question,
            )
            return on_human_checkpoint(event)

        # === Phase 1: Classification (routing pattern from 03) ===
        yield ClassifyStartEvent()
        classification = await asyncio.to_thread(self._classify, topic)
        yield ClassifyDoneEvent(classification=classification)

        content_type = classification.content_type
        other_types = [t for t in ContentType if t != content_type]
        approved, feedback = await asyncio.to_thread(
            _checkpoint,
            "classification",
            "Classification",
            f"Type: {content_type.value.upper()}\n"
            f"Topic: {classification.topic}\n"
            f"Aspects: {', '.join(classification.key_aspects)}\n"
            f"Reasoning: {classification.reasoning}\n\n"
            f"Other options: {', '.join(t.value for t in other_types)}",
            f"Classified as '{content_type.value}'. Correct?",
        )
        if not approved and feedback in [t.value for t in ContentType]:
            content_type = ContentType(feedback)
            logger.info("Classification overridden to: %s", content_type.value)

        # === Phase 2: Research planning (orchestrator pattern from 05) ===
        yield PlanStartEvent()
        subtopics = await asyncio.to_thread(
            self._plan, topic, content_type, classification.key_aspects
        )
        yield PlanDoneEvent(subtopics=subtopics)

        # === Phase 3: Parallel research (worker pattern from 05) ===
        yield ResearchStartEvent(count=len(subtopics))

        def _research_parallel() -> list[ResearchSection]:
            results: list[ResearchSection] = []
            with ThreadPoolExecutor(max_workers=len(subtopics)) as executor:
                futures = {
                    executor.submit(self._research_section, sub): sub.title for sub in subtopics
                }
                for future in as_completed(futures):
                    title = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as e:
                        logger.error("Research failed for %s: %s", title, e)
            return results

        sections = await asyncio.to_thread(_research_parallel)
        for section in sections:
            yield ResearchSectionDoneEvent(title=section.title, sources=section.sources)

        if not sections:
            raise ValueError("All research workers failed — cannot continue")
        yield ResearchDoneEvent(sections=sections)

        # Accumulate all sources across phases for the References section
        all_sources: list[Source] = []
        for s in sections:
            all_sources.extend(s.sources)

        # === Phase 4: Write (chaining pattern from 02) ===
        yield WriteStartEvent(iteration=1)
        draft, write_sources = await asyncio.to_thread(self._write, topic, sections, content_type)
        all_sources.extend(write_sources)
        yield WriteDoneEvent(
            iteration=1, content_length=len(draft), content=draft, sources=write_sources
        )

        # === Phase 5: Evaluate + refine loop (evaluator-optimizer from 06) ===
        yield EvaluateStartEvent(iteration=1)
        evaluation = await asyncio.to_thread(self._evaluate, topic, draft)
        yield EvaluateDoneEvent(iteration=1, evaluation=evaluation)

        iteration = 1
        if evaluation.avg_score < score_threshold:
            for iteration in range(2, max_refinements + 2):
                yield RefineStartEvent(iteration=iteration)
                feedback_text = (
                    f"Issues: {json.dumps(evaluation.issues)}\n"
                    f"Suggestions: {json.dumps(evaluation.suggestions)}"
                )
                draft, refine_sources = await asyncio.to_thread(
                    self._write,
                    topic,
                    sections,
                    content_type,
                    feedback=feedback_text,
                    previous_draft=draft,
                )
                all_sources.extend(refine_sources)
                yield WriteDoneEvent(
                    iteration=iteration,
                    content_length=len(draft),
                    content=draft,
                    sources=refine_sources,
                )

                yield EvaluateStartEvent(iteration=iteration)
                evaluation = await asyncio.to_thread(self._evaluate, topic, draft)
                yield EvaluateDoneEvent(iteration=iteration, evaluation=evaluation)

                if evaluation.avg_score >= score_threshold:
                    break

        # === Human checkpoint: final article review (with refinement loop) ===
        # When user rejects, combine evaluation issues + user feedback and refine
        # like the evaluator-optimizer pattern from 06
        human_approved = False
        human_review_rounds = 0
        max_human_reviews = 3

        while not human_approved and human_review_rounds < max_human_reviews:
            human_review_rounds += 1
            preview = draft[:500] + "..." if len(draft) > 500 else draft
            approved, user_feedback = await asyncio.to_thread(
                _checkpoint,
                "final_review",
                "Final Review",
                preview,
                "Approve article and publish?",
            )

            if approved:
                human_approved = True
                break

            # Combine evaluation issues with user feedback for targeted refinement
            feedback_parts = []
            if evaluation.issues:
                feedback_parts.append("Evaluation issues: " + "; ".join(evaluation.issues))
            if evaluation.suggestions:
                feedback_parts.append(
                    "Evaluation suggestions: " + "; ".join(evaluation.suggestions)
                )
            if user_feedback:
                feedback_parts.append(f"User feedback: {user_feedback}")

            if not feedback_parts:
                feedback_parts.append("Please improve the overall quality of the article.")

            combined_feedback = "\n".join(feedback_parts)
            logger.info("Human review round %d — refining with feedback", human_review_rounds)

            iteration += 1
            yield RefineStartEvent(iteration=iteration)
            draft, refine_sources = await asyncio.to_thread(
                self._write,
                topic,
                sections,
                content_type,
                feedback=combined_feedback,
                previous_draft=draft,
            )
            all_sources.extend(refine_sources)
            yield WriteDoneEvent(
                iteration=iteration,
                content_length=len(draft),
                content=draft,
                sources=refine_sources,
            )

            yield EvaluateStartEvent(iteration=iteration)
            evaluation = await asyncio.to_thread(self._evaluate, topic, draft)
            yield EvaluateDoneEvent(iteration=iteration, evaluation=evaluation)

        # Append References section to the final article
        # Deduplicate sources by URL, preserving order
        seen_urls: set[str] = set()
        unique_sources: list[Source] = []
        for src in all_sources:
            if src.url not in seen_urls:
                seen_urls.add(src.url)
                unique_sources.append(src)

        if unique_sources:
            refs = "\n\n---\n\n## References\n\n"
            refs += "\n".join(f"- [{s.title}]({s.url})" for s in unique_sources)
            draft += refs

        social: SocialContent | None = None
        seo: SeoResult | None = None

        if human_approved:
            # === Phase 6: Social media blast (parallelization fan-out from 04) ===
            yield SocialStartEvent()
            social = await asyncio.to_thread(self._write_social, draft)
            for name in ["linkedin", "twitter", "newsletter"]:
                content = getattr(social, name, "")
                if content and not content.startswith("Error:"):
                    yield SocialWriterDoneEvent(name=name)
            yield SocialDoneEvent(social=social)

            # === Phase 7: SEO title voting (parallelization voting from 04) ===
            yield SeoStartEvent()
            seo = await asyncio.to_thread(self._generate_seo, draft)
            for title in seo.candidates:
                yield SeoCandidateEvent(title=title)
            yield SeoDoneEvent(seo=seo)

        # === Complete ===
        title_line = next((ln.strip("# ") for ln in draft.split("\n") if ln.strip()), topic)
        yield CompleteEvent(
            result=WritingResult(
                content_type=content_type,
                title=title_line,
                content=draft,
                final_score=evaluation.avg_score,
                iterations=iteration,
                sources=unique_sources,
                social=social,
                seo=seo,
            )
        )
