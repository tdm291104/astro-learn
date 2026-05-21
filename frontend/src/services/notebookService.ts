import { API_ENDPOINTS } from "@/lib/constants";
import { api } from "@/services/api";
import type {
  DocumentContentResponse,
  DocumentUploadResponse,
  FlashcardRequest,
  FlashcardResponse,
  Notebook,
  NotebookArtifactKind,
  NotebookArtifactPayload,
  NotebookCreateRequest,
  NotebookListResponse,
  NotebookShareResponse,
  NotebookUpdateRequest,
  QARequest,
  QAResponse,
  QuizRequest,
  QuizResponse,
  ShareSettings,
  ShareSettingsUpdateRequest,
  SharedNotebookResponse,
  SummarizeRequest,
  SummarizeResponse,
} from "@/types/notebook.types";

// Public URL the iframe loads directly; token IS the credential.
export function sharedDocumentFileUrl(token: string, documentId: string): string {
  return `/api/proxy/shared/${encodeURIComponent(token)}/documents/${encodeURIComponent(documentId)}/file`;
}

export const notebookService = {
  async list(params?: { limit?: number; offset?: number }): Promise<NotebookListResponse> {
    const res = await api.get<NotebookListResponse>(API_ENDPOINTS.notebooks, {
      params,
    });
    return res.data;
  },

  async get(id: string): Promise<Notebook> {
    const res = await api.get<Notebook>(API_ENDPOINTS.notebook(id));
    return res.data;
  },

  async create(data: NotebookCreateRequest): Promise<Notebook> {
    // Normalize blank description to null.
    const payload: NotebookCreateRequest = {
      title: data.title.trim(),
      description: data.description?.trim() ? data.description.trim() : null,
    };
    const res = await api.post<Notebook>(API_ENDPOINTS.notebooks, payload);
    return res.data;
  },

  async update(id: string, data: NotebookUpdateRequest): Promise<Notebook> {
    // Pass through explicit nulls to allow clearing.
    const payload: NotebookUpdateRequest = {};
    if (data.title !== undefined) {
      payload.title = data.title === null ? null : data.title.trim();
    }
    if (data.description !== undefined) {
      payload.description =
        data.description === null
          ? null
          : data.description.trim()
            ? data.description.trim()
            : null;
    }
    const res = await api.patch<Notebook>(API_ENDPOINTS.notebook(id), payload);
    return res.data;
  },

  async remove(id: string): Promise<void> {
    await api.delete(API_ENDPOINTS.notebook(id));
  },

  // Idempotent on backend; does not rotate the URL.
  async createShareLink(id: string): Promise<NotebookShareResponse> {
    const res = await api.post<NotebookShareResponse>(
      API_ENDPOINTS.notebookShare(id),
    );
    return res.data;
  },

  async revokeShareLink(id: string): Promise<void> {
    await api.delete(API_ENDPOINTS.notebookShare(id));
  },

  async getShareSettings(id: string): Promise<ShareSettings> {
    const res = await api.get<ShareSettings>(
      API_ENDPOINTS.notebookShareSettings(id),
    );
    return res.data;
  },

  async updateShareSettings(
    id: string,
    body: ShareSettingsUpdateRequest,
  ): Promise<ShareSettings> {
    const res = await api.patch<ShareSettings>(
      API_ENDPOINTS.notebookShareSettings(id),
      body,
    );
    return res.data;
  },

  // Token IS the credential; route is unauthenticated.
  async getShared(token: string): Promise<SharedNotebookResponse> {
    const res = await api.get<SharedNotebookResponse>(
      API_ENDPOINTS.sharedNotebook(token),
    );
    return res.data;
  },

  async getSharedArtifact(
    token: string,
    kind: NotebookArtifactKind,
  ): Promise<NotebookArtifactPayload | null> {
    const res = await api.get<NotebookArtifactPayload | null>(
      API_ENDPOINTS.sharedArtifact(token, kind),
    );
    return res.data ?? null;
  },

  async askQuestion(
    notebookId: string,
    body: QARequest,
  ): Promise<QAResponse> {
    const res = await api.post<QAResponse>(
      API_ENDPOINTS.qa(notebookId),
      body,
    );
    return res.data;
  },

  async summarize(
    notebookId: string,
    body: SummarizeRequest,
  ): Promise<SummarizeResponse> {
    const res = await api.post<SummarizeResponse>(
      API_ENDPOINTS.summarize(notebookId),
      body,
    );
    return res.data;
  },

  async generateQuiz(
    notebookId: string,
    body: QuizRequest,
  ): Promise<QuizResponse> {
    const res = await api.post<QuizResponse>(
      API_ENDPOINTS.quiz(notebookId),
      body,
    );
    return res.data;
  },

  async generateFlashcards(
    notebookId: string,
    body: FlashcardRequest,
  ): Promise<FlashcardResponse> {
    const res = await api.post<FlashcardResponse>(
      API_ENDPOINTS.flashcards(notebookId),
      body,
    );
    return res.data;
  },

  async getArtifact(
    notebookId: string,
    kind: NotebookArtifactKind,
  ): Promise<NotebookArtifactPayload | null> {
    const res = await api.get<NotebookArtifactPayload | null>(
      API_ENDPOINTS.notebookArtifact(notebookId, kind),
    );
    // Backend returns null body (not 404) when nothing cached.
    return res.data ?? null;
  },

  async listDocuments(notebookId: string): Promise<DocumentUploadResponse[]> {
    const res = await api.get<DocumentUploadResponse[]>(
      API_ENDPOINTS.notebookDocuments(notebookId),
    );
    return res.data;
  },

  async getDocumentContent(
    notebookId: string,
    documentId: string,
  ): Promise<DocumentContentResponse> {
    const res = await api.get<DocumentContentResponse>(
      API_ENDPOINTS.notebookDocumentContent(notebookId, documentId),
    );
    return res.data;
  },

  async deleteDocument(
    notebookId: string,
    documentId: string,
  ): Promise<void> {
    await api.delete(API_ENDPOINTS.notebookDocument(notebookId, documentId));
  },

  async uploadDocument(
    notebookId: string,
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<DocumentUploadResponse> {
    const form = new FormData();
    form.append("file", file);

    const res = await api.post<DocumentUploadResponse>(
      API_ENDPOINTS.uploadDocument(notebookId),
      form,
      {
        // Let browser set multipart boundary.
        headers: { "Content-Type": undefined },
        onUploadProgress: (e) => {
          if (!onProgress) return;
          const total = e.total ?? file.size;
          if (total > 0) {
            onProgress(Math.min(100, Math.round((e.loaded / total) * 100)));
          }
        },
      },
    );
    return res.data;
  },
};
