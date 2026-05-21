"""Recursive character splitter for document chunking.

Splits text on a hierarchy of separators (`\\n\\n` -> `\\n` -> `. ` -> ` `),
recursing into oversized pieces, then merging small consecutive pieces back
into chunks of ~`size` characters with `overlap`-character overlap.

Compared to fixed-window char slicing:
  - never cuts mid-word
  - preserves paragraph / sentence boundaries when possible

Ported from the RAG retrieval evaluation where it tied with char-window
on the 16-question astronomy dataset but produced cleaner chunk text. Used
by workers/notebook_worker._build_chunks.
"""

from __future__ import annotations

# Default separators, ordered coarsest -> finest. Empty string forces hard
# character split as the last resort.
_DEFAULT_SEPARATORS: tuple[str, ...] = ("\n\n", "\n", ". ", " ", "")


class RecursiveCharacterSplitter:
    """Hierarchy-aware text splitter.

    `split_with_positions(text)` returns `[(chunk, char_offset)]` so callers
    can map chunks back to source positions (e.g. PDF page numbers).
    """

    def __init__(
        self,
        *,
        size: int = 1000,
        overlap: int = 150,
        separators: tuple[str, ...] = _DEFAULT_SEPARATORS,
    ) -> None:
        if overlap >= size:
            raise ValueError(f"overlap ({overlap}) must be < size ({size})")
        self.size = size
        self.overlap = overlap
        self.separators = separators

    def split_with_positions(self, text: str) -> list[tuple[str, int]]:
        """Split text and locate each chunk's start offset in the original."""
        if not text.strip():
            return []
        pieces = self._split(text, list(self.separators))
        pieces = self._merge(pieces, self._best_separator(text))

        out: list[tuple[str, int]] = []
        cursor = 0
        for piece in pieces:
            stripped = piece.strip()
            if not stripped:
                continue
            offset = self._locate(text, stripped, cursor)
            out.append((stripped, offset))
            cursor = max(cursor, offset + max(1, len(stripped) - self.overlap))
        return out

    # ---- internals ----

    def _best_separator(self, text: str) -> str:
        for sep in self.separators:
            if sep == "" or sep in text:
                return sep
        return ""

    def _split(self, text: str, separators: list[str]) -> list[str]:
        if not text:
            return []
        if len(text) <= self.size:
            return [text]

        separator = ""
        new_separators: list[str] = []
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break

        if separator == "":
            return self._hard_split(text)

        splits = text.split(separator)
        out: list[str] = []
        for s in splits:
            if len(s) < self.size:
                out.append(s)
            elif new_separators:
                out.extend(self._split(s, new_separators))
            else:
                out.extend(self._hard_split(s))
        return out

    def _merge(self, splits: list[str], separator: str) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        sep_len = len(separator)

        for s in splits:
            if not s:
                continue
            extra = (sep_len if current else 0) + len(s)
            if current_len + extra <= self.size:
                if current:
                    current.append(separator)
                    current_len += sep_len
                current.append(s)
                current_len += len(s)
                continue

            if current:
                chunks.append("".join(current))
            if self.overlap > 0 and chunks:
                tail = chunks[-1][-self.overlap:]
                if len(tail) + sep_len + len(s) <= self.size:
                    current = [tail, separator, s] if separator else [tail, s]
                    current_len = len(tail) + sep_len + len(s)
                else:
                    current = [s]
                    current_len = len(s)
            else:
                current = [s]
                current_len = len(s)

        if current:
            chunks.append("".join(current))
        return chunks

    def _hard_split(self, text: str) -> list[str]:
        step = self.size - self.overlap
        out: list[str] = []
        for i in range(0, len(text), step):
            piece = text[i:i + self.size]
            if piece:
                out.append(piece)
            if i + self.size >= len(text):
                break
        return out

    @staticmethod
    def _locate(text: str, piece: str, start: int) -> int:
        """Find piece at/after `start`; fall back to a 75%-suffix search."""
        pos = text.find(piece, start)
        if pos >= 0:
            return pos
        # Overlap-merged pieces may not be a contiguous slice of the original;
        # try locating a distinctive tail.
        suffix = piece[len(piece) // 4:]
        pos = text.find(suffix, start)
        if pos < 0:
            return start
        return max(start, pos - len(piece) // 4)
