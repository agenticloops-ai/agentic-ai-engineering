"""Text chunking with recursive splitting and overlap."""

from dataclasses import dataclass, field


@dataclass
class Chunk:
    """A chunk of text with source metadata."""

    content: str
    source: str
    chunk_index: int
    start_char: int
    end_char: int
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Unique identifier for this chunk."""
        return f"{self.source}:{self.chunk_index}"


# Separators tried in order — split on the most meaningful boundary first
DEFAULT_SEPARATORS = ["\n\n", "\n", ". ", " "]


def recursive_split(
    text: str,
    source: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separators: list[str] | None = None,
) -> list[Chunk]:
    """Split text recursively on natural boundaries with overlap.

    Tries separators in order: double newline, single newline, sentence end,
    space. Falls back to character split as last resort.
    """
    if not text.strip():
        return []

    seps = separators or DEFAULT_SEPARATORS
    raw_chunks = _split_recursive(text, chunk_size, seps)

    # Add overlap between consecutive chunks
    chunks = []
    for i, raw in enumerate(raw_chunks):
        # Prepend tail of previous chunk as overlap
        if i > 0 and chunk_overlap > 0:
            prev = raw_chunks[i - 1]
            overlap_text = prev[-chunk_overlap:]
            raw = overlap_text + raw

        start_char = (
            text.find(raw_chunks[i][:50]) if i == 0 else max(0, text.find(raw_chunks[i][:50]))
        )
        chunks.append(
            Chunk(
                content=raw.strip(),
                source=source,
                chunk_index=i,
                start_char=start_char,
                end_char=start_char + len(raw_chunks[i]),
            )
        )

    return [c for c in chunks if c.content]


def _split_recursive(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    """Recursively split text using progressively finer separators."""
    if len(text) <= chunk_size:
        return [text]

    # Try each separator in order
    for sep in separators:
        if sep in text:
            parts = text.split(sep)
            result = []
            current = ""

            for part in parts:
                candidate = current + sep + part if current else part
                if len(candidate) <= chunk_size:
                    current = candidate
                else:
                    if current:
                        result.append(current)
                    # If a single part exceeds chunk_size, split it with finer separators
                    if len(part) > chunk_size:
                        remaining_seps = separators[separators.index(sep) + 1 :]
                        if remaining_seps:
                            result.extend(_split_recursive(part, chunk_size, remaining_seps))
                        else:
                            # Last resort: hard split by characters
                            for j in range(0, len(part), chunk_size):
                                result.append(part[j : j + chunk_size])
                    else:
                        current = part

            if current:
                result.append(current)

            return result

    # No separator found — hard split
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
