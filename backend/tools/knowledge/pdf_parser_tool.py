"""PDF text + metadata extraction via pypdf."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, model_validator

from core.exceptions import NotFoundError, ToolError
from tools.base_tool import BaseTool


class PdfParserInput(BaseModel):
    """Provide file_id OR path."""

    file_id: uuid.UUID | None = None
    path: str | None = None
    extract_metadata: bool = True
    extract_text: bool = True
    page_range: tuple[int, int] | None = None  # 1-indexed inclusive

    @model_validator(mode="after")
    def _file_id_or_path(self) -> PdfParserInput:
        if self.file_id is None and not self.path:
            raise ValueError("Provide either `file_id` or `path`.")
        return self


class PdfPage(BaseModel):
    page_number: int = Field(..., ge=1)
    text: str
    char_offset: int = Field(..., ge=0)  # offset in concatenated text


class PdfParseResult(BaseModel):
    page_count: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    pages: list[PdfPage] = Field(default_factory=list)
    full_text: str = ""


class PdfParserTool(BaseTool):
    """Extract text + metadata from a PDF."""

    name: ClassVar[str] = "pdf_parser"
    description: ClassVar[str] = (
        "Extract text and metadata from a PDF file. Returns per-page text "
        "with character offsets so callers can build citations."
    )
    input_schema: ClassVar[type[BaseModel]] = PdfParserInput

    def __init__(self, storage_root: Path) -> None:
        self.storage_root = storage_root

    async def execute(self, **kwargs: Any) -> PdfParseResult:
        target = self._resolve_path(file_id=kwargs.get("file_id"), path=kwargs.get("path"))
        if not target.exists():
            raise NotFoundError(
                message=f"PDF not found at {target}",
                code="pdf_not_found",
            )
        return await asyncio.to_thread(
            self._parse_sync,
            target,
            extract_metadata=kwargs.get("extract_metadata", True),
            extract_text=kwargs.get("extract_text", True),
            page_range=kwargs.get("page_range"),
        )

    def _resolve_path(self, *, file_id: uuid.UUID | None, path: str | None) -> Path:
        """Resolve to abs path; relative joins storage_root."""
        if file_id is not None:
            return self.storage_root / "documents" / f"{file_id}.pdf"
        assert path is not None  # validator guarantees
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.storage_root / candidate

    @staticmethod
    def _parse_sync(
        target: Path,
        *,
        extract_metadata: bool,
        extract_text: bool,
        page_range: tuple[int, int] | None,
    ) -> PdfParseResult:
        # Lazy import: pypdf cold-import ~50ms.
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(str(target))
        except (PdfReadError, ValueError) as exc:
            raise ToolError(
                message=f"Not a valid PDF: {target}",
                code="pdf_invalid",
            ) from exc

        page_count = len(reader.pages)

        # Clamp 1-indexed inclusive page_range to actual pages.
        if page_range is None:
            start, end = 1, page_count
        else:
            start, end = page_range
            start = max(1, start)
            end = min(page_count, end)

        metadata: dict[str, Any] = {}
        if extract_metadata and reader.metadata is not None:
            for key, value in reader.metadata.items():
                # PDF dict keys are "/Title"; normalise to "title".
                clean_key = key.lstrip("/").lower() if isinstance(key, str) else str(key)
                metadata[clean_key] = str(value) if value is not None else None

        pages: list[PdfPage] = []
        full_text_parts: list[str] = []
        char_offset = 0

        if extract_text and start <= end:
            for page_num in range(start, end + 1):
                # pypdf is 0-indexed.
                text = reader.pages[page_num - 1].extract_text() or ""
                pages.append(
                    PdfPage(page_number=page_num, text=text, char_offset=char_offset)
                )
                full_text_parts.append(text)
                char_offset += len(text) + 1  # +1 for "\n" joiner

        full_text = "\n".join(full_text_parts) if full_text_parts else ""

        return PdfParseResult(
            page_count=page_count,
            metadata=metadata,
            pages=pages,
            full_text=full_text,
        )
