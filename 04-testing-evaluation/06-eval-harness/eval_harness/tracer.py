"""Lightweight trace collector for the eval harness."""

import logging
import time

from eval_harness.models import TraceSpan

logger = logging.getLogger(__name__)


class SimpleTracer:
    """Lightweight trace collector that records spans during eval execution."""

    def __init__(self) -> None:
        self._spans: list[TraceSpan] = []
        self._active_spans: list[TraceSpan] = []

    def start_span(self, name: str, span_type: str) -> TraceSpan:
        """Start a new trace span and return it."""
        span = TraceSpan(
            name=name,
            span_type=span_type,
            start_time=time.time(),
        )

        # Nest under the current active span if one exists
        if self._active_spans:
            self._active_spans[-1].children.append(span)
        else:
            self._spans.append(span)

        self._active_spans.append(span)
        logger.debug("Span started: %s (%s)", name, span_type)
        return span

    def end_span(self, span: TraceSpan) -> None:
        """End a trace span by recording its end time."""
        span.end_time = time.time()

        if self._active_spans and self._active_spans[-1] is span:
            self._active_spans.pop()

        logger.debug("Span ended: %s (%.1fms)", span.name, span.duration_ms)

    def get_spans(self) -> list[TraceSpan]:
        """Return all collected root-level spans."""
        return list(self._spans)

    def reset(self) -> None:
        """Clear all collected spans."""
        self._spans.clear()
        self._active_spans.clear()

    def get_total_duration_ms(self) -> float:
        """Sum the durations of all root spans."""
        return sum(s.duration_ms for s in self._spans)

    def get_span_count(self) -> int:
        """Count all spans including nested children."""
        count = 0

        def _count(spans: list[TraceSpan]) -> None:
            nonlocal count
            for span in spans:
                count += 1
                _count(span.children)

        _count(self._spans)
        return count
