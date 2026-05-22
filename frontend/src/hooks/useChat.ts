"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { useAgentStream } from "@/hooks/useAgentStream";
import { analysisKeys } from "@/hooks/useAnalysis";
import { sessionKeys } from "@/hooks/useSessions";
import { useAstronomyStore } from "@/stores/astronomyStore";
import { useLocaleStore } from "@/stores/localeStore";
import {
  useChatStore,
  type CatalogGrounding,
  type CatalogGroundingRow,
  type CatalogGroundingWebSource,
  type ChatMessage,
  type PlannedStepInfo,
  type ReasoningPayload,
  type WebSearchResult,
} from "@/stores/chatStore";
import type { AgentMessage } from "@/types/agent.types";
import type { AnalysisType } from "@/types/astronomy.types";
import type { Citation } from "@/types/notebook.types";

// Marker from OrchestratorAgent._step_notice; rendered as inline pill.
const STEP_NOTICE_PREFIX = "→ Running:";

// Mirror of _DISPATCH_TYPE in fits_analyst_agent.py.
const DECISION_TO_ANALYSIS_TYPE: Record<string, AnalysisType> = {
  image_stats: "image_stats",
  photometry: "photometry",
  spectroscopy: "spectroscopy",
  wcs: "wcs_solve",
  custom: "custom",
};

// crypto.randomUUID to avoid collisions on bursty streams.
function newId(prefix: string): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function isStepNotice(content: string): boolean {
  return content.trimStart().startsWith(STEP_NOTICE_PREFIX);
}

// Prune stale FITS entry when agent reports fits_not_found.
function pruneStaleFitsFileIfPresent(msg: AgentMessage): void {
  if (msg.role !== "assistant") return;
  const extra = msg.extra ?? {};
  if (extra.error_kind !== "fits_not_found") return;
  const missing = extra.missing_file_id;
  if (typeof missing !== "string" || !missing) return;
  useAstronomyStore.getState().removeRecentFile(missing);
}

// Surface analysis_id from FITS tool frames so the right-rail card mounts.
function surfaceAnalysisIdIfPresent(
  msg: AgentMessage,
  runAnalysisIds: Set<string>,
): void {
  if (msg.role !== "tool") return;
  const extra = msg.extra ?? {};
  const analysisId =
    typeof extra.analysis_id === "string" ? extra.analysis_id : null;
  if (!analysisId) return;
  const decisionToken =
    typeof extra.analysis_type === "string" ? extra.analysis_type : "image_stats";
  const analysisType: AnalysisType =
    DECISION_TO_ANALYSIS_TYPE[decisionToken] ?? "image_stats";

  // Fall back to currently selected file since extras don't carry file_id.
  const fileId = useAstronomyStore.getState().selectedFileId ?? "";
  if (!fileId) return;

  // Only first analysis enters MRU; multiple in one run share same interpretation.
  if (runAnalysisIds.size === 0) {
    useAstronomyStore.getState().addRecentAnalysis({
      id: analysisId,
      type: analysisType,
      fileId,
    });
  }
  runAnalysisIds.add(analysisId);
}

// Invalidate analysis polling cache once final interpretation persists.
function maybeInvalidateAnalysisCache(
  msg: AgentMessage,
  runAnalysisIds: Set<string>,
  qc: ReturnType<typeof useQueryClient>,
): void {
  if (msg.role !== "assistant") return;
  const extra = msg.extra ?? {};
  if (!extra.fits_interpretation) return;
  if (runAnalysisIds.size === 0) return;
  for (const id of runAnalysisIds) {
    qc.invalidateQueries({ queryKey: analysisKeys.detail(id) });
  }
  runAnalysisIds.clear();
}

// Convert an SSE AgentMessage into a UI ChatMessage.
function toChatMessage(msg: AgentMessage): ChatMessage {
  const stepLike = msg.role === "system" && isStepNotice(msg.content);
  // chat_error → render warning variant on the fallback string.
  const extra = msg.extra ?? {};
  const isError = extra.chat_error === true;
  const errorKind =
    typeof extra.error_kind === "string" ? extra.error_kind : undefined;
  const citations = extractCitations(extra.citations);
  const catalogGrounding = extractCatalogGrounding(extra.catalog_grounding);
  const webSearchResults = extractWebSearchResults(extra.web_search_results);
  const webSearchQuery =
    typeof extra.web_search_query === "string"
      ? extra.web_search_query
      : undefined;
  const reasoning = extractReasoning(extra);
  const confirmWebSearch = extractConfirmWebSearch(extra);
  const suggestPanel = extractSuggestPanel(extra);
  const suggestMode = extractSuggestMode(extra);
  return {
    id: msg.id || newId(msg.role),
    role: msg.role,
    content: msg.content,
    agentName: msg.name ?? undefined,
    isStep: stepLike || undefined,
    isProgress: extra.is_progress === true || undefined,
    reasoning,
    toolCalls: msg.tool_calls ?? undefined,
    toolCallId: msg.tool_call_id ?? undefined,
    isError: isError || undefined,
    errorKind,
    citations,
    catalogGrounding,
    webSearchResults,
    webSearchQuery,
    confirmWebSearch,
    suggestPanel,
    suggestMode,
    createdAt: msg.created_at || new Date().toISOString(),
  };
}

function extractWebSearchResults(raw: unknown): WebSearchResult[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const out: WebSearchResult[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    if (typeof r.url !== "string" || !r.url) continue;
    out.push({
      title: typeof r.title === "string" && r.title ? r.title : r.url,
      url: r.url,
      snippet: typeof r.snippet === "string" ? r.snippet : "",
      source: typeof r.source === "string" && r.source ? r.source : null,
    });
  }
  return out.length > 0 ? out : undefined;
}

// Read `extra.suggest_mode` shape from orchestrator mode-hint replies.
function extractSuggestMode(
  extra: Record<string, unknown>,
): ChatMessage["suggestMode"] {
  const target = extra.suggest_mode;
  if (
    target !== "general" &&
    target !== "notebook" &&
    target !== "fits" &&
    target !== "catalog"
  ) {
    return undefined;
  }
  const reason = typeof extra.reason === "string" ? extra.reason : null;
  return { targetMode: target, reason };
}

// Read `extra.suggest_panel` shape from notebook-tool orchestrator redirects.
function extractSuggestPanel(
  extra: Record<string, unknown>,
): ChatMessage["suggestPanel"] {
  const panel = extra.suggest_panel;
  if (panel !== "summary" && panel !== "quiz" && panel !== "flashcards") {
    return undefined;
  }
  const notebookId =
    typeof extra.notebook_id === "string" ? extra.notebook_id : null;
  return {
    panel,
    notebookId,
    autoOpen: extra.auto_open === true,
  };
}

// Read `extra.action === "confirm_web_search"` shape into a typed payload.
function extractConfirmWebSearch(
  extra: Record<string, unknown>,
): { query: string } | undefined {
  if (extra.action !== "confirm_web_search") return undefined;
  const q = typeof extra.query === "string" ? extra.query.trim() : "";
  if (!q) return undefined;
  return { query: q };
}

function extractCatalogGrounding(raw: unknown): CatalogGrounding | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const g = raw as Record<string, unknown>;
  if (
    typeof g.query !== "string" ||
    typeof g.source !== "string" ||
    typeof g.row_count !== "number"
  ) {
    return undefined;
  }
  const rowsRaw = Array.isArray(g.rows) ? g.rows : [];
  const rows: CatalogGroundingRow[] = [];
  for (const item of rowsRaw) {
    if (!item || typeof item !== "object") continue;
    const r = item as Record<string, unknown>;
    if (typeof r.name !== "string") continue;
    rows.push({
      name: r.name,
      object_type: typeof r.object_type === "string" ? r.object_type : null,
      ra_deg: typeof r.ra_deg === "number" ? r.ra_deg : null,
      dec_deg: typeof r.dec_deg === "number" ? r.dec_deg : null,
    });
  }
  const webRaw = Array.isArray(g.web_sources) ? g.web_sources : null;
  let webSources: CatalogGroundingWebSource[] | undefined;
  if (webRaw && webRaw.length > 0) {
    const accum: CatalogGroundingWebSource[] = [];
    for (const item of webRaw) {
      if (!item || typeof item !== "object") continue;
      const w = item as Record<string, unknown>;
      if (typeof w.url !== "string" || !w.url) continue;
      accum.push({
        title: typeof w.title === "string" ? w.title : w.url,
        url: w.url,
      });
    }
    if (accum.length > 0) webSources = accum;
  }
  return {
    query: g.query,
    source: g.source,
    row_count: g.row_count,
    rows,
    web_sources: webSources,
  };
}

// Narrow `extra.step_kind=plan|step` extras into a typed payload for the UI.
function extractReasoning(extra: Record<string, unknown>): ReasoningPayload | undefined {
  const kind = extra.step_kind;
  if (kind === "plan") {
    const stepsRaw = Array.isArray(extra.steps) ? extra.steps : [];
    const steps: PlannedStepInfo[] = [];
    for (const item of stepsRaw) {
      if (!item || typeof item !== "object") continue;
      const s = item as Record<string, unknown>;
      if (typeof s.agent_name !== "string") continue;
      steps.push({
        agent_name: s.agent_name,
        rationale: typeof s.rationale === "string" ? s.rationale : null,
      });
    }
    return {
      kind: "plan",
      summary: typeof extra.summary === "string" ? extra.summary : null,
      steps,
    };
  }
  if (kind === "step" && typeof extra.agent_name === "string") {
    return {
      kind: "step",
      index: typeof extra.step_index === "number" ? extra.step_index : 0,
      total: typeof extra.step_total === "number" ? extra.step_total : 1,
      agent_name: extra.agent_name,
      rationale:
        typeof extra.rationale === "string" ? extra.rationale : null,
    };
  }
  return undefined;
}

// Defensive narrowing; malformed extras must not crash the chat list.
function extractCitations(raw: unknown): Citation[] | undefined {
  if (!Array.isArray(raw) || raw.length === 0) return undefined;
  const out: Citation[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const c = item as Record<string, unknown>;
    if (typeof c.document_id !== "string" || typeof c.snippet !== "string") continue;
    out.push({
      document_id: c.document_id,
      chunk_id: typeof c.chunk_id === "string" ? c.chunk_id : "",
      snippet: c.snippet,
      score: typeof c.score === "number" ? c.score : 0,
    });
  }
  return out.length > 0 ? out : undefined;
}

export function useChat() {
  const stream = useAgentStream();
  const qc = useQueryClient();
  const addMessage = useChatStore((s) => s.addMessage);
  const setStreaming = useChatStore((s) => s.setStreaming);
  const setReconnecting = useChatStore((s) => s.setReconnecting);
  const messages = useChatStore((s) => s.messages);

  // Cursor for mirroring; reset whenever stream array shrinks.
  const mirroredCountRef = useRef(0);
  // Analysis ids surfaced this run; consumed when final interpretation arrives.
  const runAnalysisIdsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if (stream.messages.length < mirroredCountRef.current) {
      mirroredCountRef.current = 0;
    }
    if (stream.messages.length === mirroredCountRef.current) return;

    const fresh = stream.messages.slice(mirroredCountRef.current);
    for (const m of fresh) {
      surfaceAnalysisIdIfPresent(m, runAnalysisIdsRef.current);
      pruneStaleFitsFileIfPresent(m);
      maybeInvalidateAnalysisCache(m, runAnalysisIdsRef.current, qc);
      // Drop orchestrator's user echo; we already rendered a friendly bubble.
      if (m.role === "user") continue;
      addMessage(toChatMessage(m));
    }
    mirroredCountRef.current = stream.messages.length;
  }, [stream.messages, addMessage, qc]);

  useEffect(() => {
    setStreaming(stream.isStreaming);
  }, [stream.isStreaming, setStreaming]);

  useEffect(() => {
    setReconnecting(stream.isReconnecting);
  }, [stream.isReconnecting, setReconnecting]);

  const send = useCallback(
    async (rawText: string, options?: { forceWebSearch?: boolean }) => {
      const text = rawText.trim();
      if (!text) return;

      const { ensureSessionId, notebookId, mode } = useChatStore.getState();

      // Optimistic user turn so composer empties before network call.
      const userMsg: ChatMessage = {
        id: newId("u"),
        role: "user",
        content: text,
        createdAt: new Date().toISOString(),
      };
      addMessage(userMsg);

      // Need a session row before orchestrator persists messages.
      let sessionId: string;
      try {
        sessionId = await ensureSessionId();
      } catch {
        return;
      }

      // History lives server-side; task_input only carries this turn.
      // Always pass the active mode so backend rules (mode-mismatch hint,
      // resource binding guards) see the same context the user sees.
      // locale follows the i18n switcher so notebook outputs (summary,
      // quiz, flashcards) match the UI language regardless of source-doc
      // language.
      const locale = useLocaleStore.getState().locale;
      const taskInput: Record<string, unknown> = { query: text, mode, locale };
      // Only attach notebook_id in notebook mode to avoid leaking it.
      if (mode === "notebook" && notebookId) {
        taskInput.notebook_id = notebookId;
      }
      // file_id required for _rule_fits_mode_to_fits_analyst; mode itself
      // already attached above so the binding-guard hint can fire when
      // the user picked no file yet.
      if (mode === "fits") {
        const { selectedFileId, selectedHduIndex } = useAstronomyStore.getState();
        if (selectedFileId) {
          taskInput.file_id = selectedFileId;
          taskInput.hdu_index = selectedHduIndex;
        }
        // Toolbar pin overrides the backend text-classifier; null = auto.
        const intent = useChatStore.getState().fitsIntent;
        if (intent) {
          taskInput.intent = intent;
        }
      }
      // Attach last results so _rule_catalog_followup picks CatalogChatAgent;
      // also drives _rule_catalog_mode_search when no previous results exist.
      if (mode === "catalog") {
        const last = useChatStore.getState().lastCatalogSearch;
        if (last && last.results.length > 0) {
          taskInput.catalog_query = last.query;
          taskInput.catalog_source = last.source;
          taskInput.catalog_results = last.results;
        }
      }
      // User opted into web fallback after an empty catalog search.
      if (options?.forceWebSearch) {
        taskInput.force_web_search = true;
      }

      mirroredCountRef.current = 0;
      runAnalysisIdsRef.current = new Set();
      stream.start({
        agent_name: "orchestrator",
        task_input: taskInput,
        // session_id keys ConversationMemory in Redis.
        session_id: sessionId,
      });
      // Refresh History so the new session appears immediately.
      qc.invalidateQueries({ queryKey: sessionKeys.all });
    },
    [addMessage, stream, qc],
  );

  const stop = useCallback(() => {
    stream.stop();
  }, [stream]);

  return {
    messages,
    isStreaming: stream.isStreaming,
    isReconnecting: stream.isReconnecting,
    error: stream.error,
    streamPhase: stream.streamPhase,
    send,
    stop,
  };
}
