// Next.js app router paths.
export const ROUTES = {
  home: "/",
  login: "/login",
  register: "/register",
  dashboard: "/dashboard",
  // Notebooks folded into /chat?mode=notebook; helpers keep old names.
  notebooks: "/chat?mode=notebook",
  notebook: (id: string) =>
    `/chat?mode=notebook&nb=${encodeURIComponent(id)}`,
  sharedNotebook: (token: string) => `/shared/${token}`,
  chat: "/chat",
  costs: "/costs",
  profile: "/profile",
  admin: "/admin",
  adminUsers: "/admin/users",
  adminUser: (id: string) => `/admin/users/${id}`,
  adminAgentRuns: "/admin/agent-runs",
  adminCosts: "/admin/costs",
  adminNotebooks: "/admin/notebooks",
  adminFits: "/admin/fits",
} as const;

// Paths relative to the /api/proxy base.
export const API_ENDPOINTS = {
  register: "/users/register",
  login: "/users/login",
  me: "/users/me",
  meStats: "/users/me/stats",
  changePassword: "/users/me/password",
  tokenUsage: "/users/me/token-usage",
  costBreakdown: "/users/me/cost-breakdown",
  // Collection paths have no trailing slash; proxy follows FastAPI's 307.
  notebooks: "/notebooks",
  notebook: (id: string) => `/notebooks/${id}`,
  notebookDocuments: (id: string) => `/notebooks/${id}/documents`,
  notebookDocument: (id: string, docId: string) =>
    `/notebooks/${id}/documents/${docId}`,
  notebookDocumentContent: (id: string, docId: string) =>
    `/notebooks/${id}/documents/${docId}/content`,
  notebookDocumentFile: (id: string, docId: string) =>
    `/notebooks/${id}/documents/${docId}/file`,
  uploadDocument: (id: string) => `/notebooks/${id}/upload`,
  qa: (id: string) => `/notebooks/${id}/qa`,
  summarize: (id: string) => `/notebooks/${id}/summarize`,
  quiz: (id: string) => `/notebooks/${id}/quiz`,
  flashcards: (id: string) => `/notebooks/${id}/flashcards`,
  notebookArtifact: (id: string, kind: string) =>
    `/notebooks/${id}/artifacts/${kind}`,
  notebookShare: (id: string) => `/notebooks/${id}/share`,
  notebookShareSettings: (id: string) => `/notebooks/${id}/share/settings`,
  sharedNotebook: (token: string) => `/shared/${token}`,
  sharedDocumentFile: (token: string, docId: string) =>
    `/shared/${token}/documents/${docId}/file`,
  sharedArtifact: (token: string, kind: string) =>
    `/shared/${token}/artifacts/${kind}`,
  sessions: "/sessions",
  session: (id: string) => `/sessions/${id}`,
  sessionMessages: (id: string) => `/sessions/${id}/messages`,
  sessionFiles: (id: string) => `/sessions/${id}/files`,
  sessionFile: (id: string, fileId: string) =>
    `/sessions/${id}/files/${fileId}`,
  agents: "/agents",
  runAgent: "/agents/run",
  agentRun: (id: string) => `/agents/${id}`,
  agentStatus: (id: string) => `/agents/${id}/status`,
  uploadFits: "/astronomy/upload-fits",
  analyze: "/astronomy/analyze",
  analyses: "/astronomy/analyses",
  analysis: (id: string) => `/astronomy/analyses/${id}`,
  catalogSearch: "/astronomy/catalog/search",
  report: "/astronomy/report",
  reportDownload: (id: string) => `/astronomy/reports/${id}/download`,
  fitsArtifact: (fileId: string, filename: string) =>
    `/astronomy/files/${fileId}/artifacts/${encodeURIComponent(filename)}`,
  fitsFile: (fileId: string) => `/astronomy/files/${fileId}`,
  fitsFiles: "/astronomy/files",
  sampleFits: "/astronomy/sample-fits",
  // Admin endpoints require is_admin=true; backend returns 403 otherwise.
  adminUsers: "/admin/users",
  adminUser: (id: string) => `/admin/users/${id}`,
  adminStatsOverview: "/admin/stats/overview",
  adminStatsCostBreakdown: "/admin/stats/cost-breakdown",
  adminAgentRuns: "/admin/agent-runs",
  adminAgentRun: (id: string) => `/admin/agent-runs/${id}`,
  adminNotebooks: "/admin/notebooks",
  adminNotebook: (id: string) => `/admin/notebooks/${id}`,
  adminFitsFiles: "/admin/fits",
  adminFitsFile: (id: string) => `/admin/fits/${id}`,
} as const;

// Hides artifact links without removing code.
export const ARTIFACTS_ENABLED = true;

// Must match backend limits.
export const MAX_FILE_SIZE = {
  document: 50 * 1024 * 1024, // 50 MiB
  fits: 500 * 1024 * 1024, // 500 MiB
} as const;

export const ACCEPTED_DOCUMENT_TYPES = [
  "application/pdf",
  "text/plain",
  "text/markdown",
] as const;

export const APP_NAME = process.env.NEXT_PUBLIC_APP_NAME ?? "AstroLearn";
