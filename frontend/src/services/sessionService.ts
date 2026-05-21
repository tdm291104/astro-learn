import { API_ENDPOINTS } from "@/lib/constants";
import { api } from "@/services/api";
import type { Message, Session, SessionMode } from "@/types/notebook.types";

export type SessionCreatePayload = {
  title?: string | null;
  mode?: SessionMode;
  notebook_id?: string | null;
};

export type SessionUpdatePayload = {
  title?: string | null;
  mode?: SessionMode;
  notebook_id?: string | null;
};

export const sessionService = {
  async list(params?: {
    notebookId?: string;
    limit?: number;
    offset?: number;
  }): Promise<Session[]> {
    const res = await api.get<Session[]>(API_ENDPOINTS.sessions, {
      params: {
        // Omit null to avoid serializing as the string "null".
        notebook_id: params?.notebookId,
        limit: params?.limit,
        offset: params?.offset,
      },
    });
    return res.data;
  },

  async create(payload: SessionCreatePayload): Promise<Session> {
    const res = await api.post<Session>(API_ENDPOINTS.sessions, payload);
    return res.data;
  },

  async get(sessionId: string): Promise<Session> {
    const res = await api.get<Session>(API_ENDPOINTS.session(sessionId));
    return res.data;
  },

  async update(
    sessionId: string,
    payload: SessionUpdatePayload,
  ): Promise<Session> {
    const res = await api.patch<Session>(
      API_ENDPOINTS.session(sessionId),
      payload,
    );
    return res.data;
  },

  async getMessages(sessionId: string): Promise<Message[]> {
    const res = await api.get<Message[]>(
      API_ENDPOINTS.sessionMessages(sessionId),
    );
    return res.data;
  },

  async attachFile(sessionId: string, fitsFileId: string): Promise<Session> {
    const res = await api.post<Session>(API_ENDPOINTS.sessionFiles(sessionId), {
      fits_file_id: fitsFileId,
    });
    return res.data;
  },

  async detachFile(sessionId: string, fitsFileId: string): Promise<void> {
    await api.delete(API_ENDPOINTS.sessionFile(sessionId, fitsFileId));
  },

  async remove(sessionId: string): Promise<void> {
    await api.delete(API_ENDPOINTS.session(sessionId));
  },
};
