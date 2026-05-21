"""Schemas for /notebooks/* endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class NotebookCreateRequest(BaseModel):
    """Body for POST /notebooks/."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)


class NotebookUpdateRequest(BaseModel):
    """Partial update body for PATCH /notebooks/{id}."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)


class NotebookResponse(BaseModel):
    """Notebook detail."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class NotebookShareResponse(BaseModel):
    """Response from POST /notebooks/{id}/share."""

    share_token: str
    # Relative fragment; frontend builds the full link.
    share_path: str


class ShareSettingsUpdateRequest(BaseModel):
    """Partial update body for PATCH /notebooks/{id}/share/settings."""

    show_filenames: bool | None = None


class ShareSettingsResponse(BaseModel):
    """Effective share settings after an update."""

    show_filenames: bool


class SharedDocument(BaseModel):
    """Lean read-only document descriptor for the public share view."""

    # Stable id so the public viewer can fetch the file by URL.
    document_id: uuid.UUID
    filename: str
    size_bytes: int
    indexed_chunks: int | None = None


class SharedNotebookResponse(BaseModel):
    """No-auth read-only notebook view returned by GET /shared/{token}."""

    title: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    document_count: int
    documents: list[SharedDocument]


# Reflects document's place in workers/notebook_worker.py pipeline.
DocumentStatus = Literal["queued", "indexing", "indexed", "failed"]


class DocumentUploadResponse(BaseModel):
    """Response from POST /notebooks/{id}/upload."""

    document_id: uuid.UUID
    notebook_id: uuid.UUID
    filename: str
    size_bytes: int
    status: DocumentStatus
    indexed_chunks: int | None = None


class DocumentPage(BaseModel):
    """One page of a PDF document; char_offset locates it in `content`."""

    page_number: int
    text: str
    char_offset: int


class DocumentContentResponse(BaseModel):
    """Response from GET /notebooks/{id}/documents/{doc_id}/content."""

    document_id: uuid.UUID
    notebook_id: uuid.UUID
    filename: str
    content_type: str | None
    size_bytes: int
    # Plain text payload; PDFs are extracted page-by-page and joined.
    content: str
    # Set when the file is too large to return in full.
    truncated: bool = False
    # PDF-only: per-page text + offsets so the viewer can paginate.
    pages: list[DocumentPage] | None = None
    page_count: int | None = None


class Citation(BaseModel):
    """A source span the answer relied on."""

    document_id: uuid.UUID
    chunk_id: str
    snippet: str
    score: float = Field(..., ge=0.0, le=1.0)
    # 1-indexed PDF page; null for non-paginated sources (.txt/.md).
    page: int | None = Field(None, ge=1)


class QARequest(BaseModel):
    """Body for POST /notebooks/{id}/qa."""

    question: str = Field(..., min_length=1, max_length=4000)
    # continue an existing thread
    session_id: uuid.UUID | None = None
    top_k: int = Field(5, ge=1, le=20)


class QAResponse(BaseModel):
    """Answer plus grounded citations."""

    answer: str
    citations: list[Citation]
    session_id: uuid.UUID
    message_id: uuid.UUID


class SummarizeRequest(BaseModel):
    """Body for POST /notebooks/{id}/summarize."""

    max_bullets: int = Field(7, ge=3, le=20)
    style: Literal["bullets", "paragraph"] = "bullets"


class SummarizeResponse(BaseModel):
    """Summary output (string for paragraph style, list for bullets)."""

    summary: str | list[str]
    source_document_count: int


class QuizItem(BaseModel):
    """One multiple-choice question — exactly 4 options, one correct."""

    question: str
    options: list[str] = Field(..., min_length=4, max_length=4)
    correct_index: int = Field(..., ge=0, le=3)
    explanation: str | None = None


class QuizRequest(BaseModel):
    """Body for POST /notebooks/{id}/quiz."""

    n_questions: int = Field(5, ge=1, le=30)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class QuizResponse(BaseModel):
    """Quiz output envelope."""

    questions: list[QuizItem]


class Flashcard(BaseModel):
    """One flashcard front/back pair."""

    front: str
    back: str


class FlashcardRequest(BaseModel):
    """Body for POST /notebooks/{id}/flashcards."""

    n_cards: int = Field(10, ge=1, le=50)


class FlashcardResponse(BaseModel):
    """Flashcard output envelope."""

    cards: list[Flashcard]


NotebookArtifactKind = Literal["summary", "quiz", "flashcards"]


class NotebookArtifactPayload(BaseModel):
    """Cached summary/quiz/flashcards payload; lets studio skip regeneration."""

    model_config = ConfigDict(from_attributes=True)

    notebook_id: uuid.UUID
    kind: NotebookArtifactKind
    params: dict[str, Any]
    payload: dict[str, Any]
    updated_at: datetime


class StudyPackRequest(BaseModel):
    """Body for POST /notebooks/{id}/study-pack."""

    max_bullets: int = Field(7, ge=3, le=20)
    n_questions: int = Field(5, ge=1, le=30)
    n_cards: int = Field(10, ge=1, le=50)


class LearningPackRequest(BaseModel):
    """Body for POST /notebooks/{id}/documents/{doc_id}/learning-pack."""

    # Tighter than study-pack: single-document input rarely yields 30 distinct items.
    n_questions: int = Field(5, ge=1, le=15)
    n_cards: int = Field(10, ge=1, le=30)


class StudyPackResponse(BaseModel):
    """Combined output of the notebook workflow."""

    summary: str | list[str] | None
    quiz: list[QuizItem]
    flashcards: list[Flashcard]
    session_id: uuid.UUID
