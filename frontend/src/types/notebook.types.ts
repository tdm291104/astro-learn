// Mirrors backend Pydantic schemas in backend/api/v1/schemas/notebook.py.
export type Notebook = {
  id: string;
  owner_id: string;
  title: string;
  description: string | null;
  created_at: string; // ISO datetime
  updated_at: string;
};

export type NotebookCreateRequest = {
  title: string;
  description?: string | null;
};

export type NotebookUpdateRequest = {
  title?: string | null;
  description?: string | null;
};

// Aliased so we can add pagination later without touching callers.
export type NotebookListResponse = Notebook[];

// share_path is relative so FE can prefix with window.location.origin.
export type NotebookShareResponse = {
  share_token: string;
  share_path: string;
};

export type ShareSettings = {
  show_filenames: boolean;
};

export type ShareSettingsUpdateRequest = {
  show_filenames?: boolean;
};

// Public-share document descriptor (metadata only).
export type SharedDocument = {
  document_id: string;
  filename: string;
  size_bytes: number;
  indexed_chunks: number | null;
};

// Strips owner_id + sessions so public links can't enumerate users.
export type SharedNotebookResponse = {
  title: string;
  description: string | null;
  created_at: string; // ISO datetime
  updated_at: string;
  document_count: number;
  documents: SharedDocument[];
};

export type DocumentStatus = "queued" | "indexing" | "indexed" | "failed";

// Shared wire shape for POST /upload and GET /documents; row `id` is `document_id`.
export type DocumentUploadResponse = {
  document_id: string;
  notebook_id: string;
  filename: string;
  size_bytes: number;
  status: DocumentStatus;
  indexed_chunks: number | null;
};

export type DocumentPage = {
  page_number: number;
  text: string;
  char_offset: number;
};

export type DocumentContentResponse = {
  document_id: string;
  notebook_id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  content: string;
  truncated: boolean;
  pages: DocumentPage[] | null;
  page_count: number | null;
};

export type Citation = {
  document_id: string;
  chunk_id: string;
  snippet: string;
  score: number; // 0.0 – 1.0
};

export type QARequest = {
  question: string;
  session_id?: string | null;
  top_k?: number; // 1–20, backend default 5
};

export type QAResponse = {
  answer: string;
  citations: Citation[];
  session_id: string;
  message_id: string;
};

export type SummarizeStyle = "bullets" | "paragraph";

export type SummarizeRequest = {
  max_bullets?: number; // 3–20, default 7
  style?: SummarizeStyle; // default "bullets"
  // FE i18n locale pins output language regardless of source-doc language.
  language?: string;
};

// `summary` is a string for paragraph style, an array of bullets otherwise.
export type SummarizeResponse = {
  summary: string | string[];
  source_document_count: number;
};

export type QuizDifficulty = "easy" | "medium" | "hard";

export type QuizItem = {
  question: string;
  options: [string, string, string, string]; // exactly 4
  correct_index: 0 | 1 | 2 | 3;
  explanation: string | null;
};

export type QuizRequest = {
  n_questions?: number; // 1–30, default 5
  difficulty?: QuizDifficulty; // default "medium"
  language?: string;
};

export type QuizResponse = {
  questions: QuizItem[];
};

export type Flashcard = {
  front: string;
  back: string;
};

export type FlashcardRequest = {
  n_cards?: number; // 1–50, default 10
  language?: string;
};

export type FlashcardResponse = {
  cards: Flashcard[];
};

// Mirror of backend NotebookArtifactKind.
export type NotebookArtifactKind = "summary" | "quiz" | "flashcards";

// Cached artifact payload; Studio fetches on mount to skip regeneration.
export type NotebookArtifactPayload = {
  notebook_id: string;
  kind: NotebookArtifactKind;
  params: Record<string, unknown>;
  payload:
    | SummarizeResponse
    | QuizResponse
    | FlashcardResponse
    | Record<string, unknown>;
  updated_at: string;
};

export type MessageRole = "system" | "user" | "assistant" | "tool";

// Mirror of backend SessionMode literal.
export type SessionMode = "general" | "notebook" | "fits" | "catalog";

export type Session = {
  id: string;
  user_id: string;
  notebook_id: string | null;
  title: string | null;
  mode: SessionMode;
  // Ids only; metadata fetched via /astronomy/files on rehydrate.
  fits_file_ids: string[];
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  session_id: string;
  role: MessageRole;
  content: string;
  extra: Record<string, unknown> | null;
  created_at: string;
};
