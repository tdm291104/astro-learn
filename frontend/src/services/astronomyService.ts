import { API_ENDPOINTS } from "@/lib/constants";
import { api } from "@/services/api";
import { useAuthStore } from "@/stores/authStore";
import type {
  AnalyzeRequest,
  AnalyzeResponse,
  CatalogSearchRequest,
  CatalogSearchResponse,
  FitsUploadResponse,
  ReportRequest,
  ReportResponse,
} from "@/types/astronomy.types";

// Anchor/SSE navigation can't set Authorization; proxy accepts ?token= fallback.
function withAuthToken(path: string): string {
  const token = useAuthStore.getState().token;
  if (!token) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}token=${encodeURIComponent(token)}`;
}

export const astronomyService = {
  async deleteFits(fileId: string): Promise<void> {
    await api.delete(API_ENDPOINTS.fitsFile(fileId));
  },

  async listFits(): Promise<FitsUploadResponse[]> {
    const res = await api.get<FitsUploadResponse[]>(API_ENDPOINTS.fitsFiles);
    return res.data;
  },

  async uploadFits(
    file: File,
    onProgress?: (percent: number) => void,
  ): Promise<FitsUploadResponse> {
    const form = new FormData();
    form.append("file", file);

    const res = await api.post<FitsUploadResponse>(
      API_ENDPOINTS.uploadFits,
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

  async analyze(body: AnalyzeRequest): Promise<AnalyzeResponse> {
    const res = await api.post<AnalyzeResponse>(API_ENDPOINTS.analyze, body);
    return res.data;
  },

  async getAnalysis(id: string): Promise<AnalyzeResponse> {
    const res = await api.get<AnalyzeResponse>(API_ENDPOINTS.analysis(id));
    return res.data;
  },

  async listAnalyses(): Promise<AnalyzeResponse[]> {
    const res = await api.get<AnalyzeResponse[]>(API_ENDPOINTS.analyses);
    return res.data;
  },

  async searchCatalog(
    params: CatalogSearchRequest,
  ): Promise<CatalogSearchResponse> {
    const res = await api.get<CatalogSearchResponse>(
      API_ENDPOINTS.catalogSearch,
      { params },
    );
    return res.data;
  },

  async generateReport(body: ReportRequest): Promise<ReportResponse> {
    const res = await api.post<ReportResponse>(API_ENDPOINTS.report, body);
    return res.data;
  },

  // Proxy URL for <a href download>; token rewritten to Bearer upstream.
  reportDownloadUrl(id: string): string {
    return withAuthToken(`/api/proxy${API_ENDPOINTS.reportDownload(id)}`);
  },

  artifactUrl(fileId: string, filename: string): string {
    return withAuthToken(`/api/proxy${API_ENDPOINTS.fitsArtifact(fileId, filename)}`);
  },
};
