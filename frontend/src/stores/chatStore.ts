import { create } from "zustand";
import { persist } from "zustand/middleware";

import { sessionService } from "@/services/sessionService";
import { useAstronomyStore } from "@/stores/astronomyStore";
import type { ToolCall } from "@/types/agent.types";
import type { CatalogObject, CatalogSource } from "@/types/astronomy.types";
import type { Citation, Session } from "@/types/notebook.types";

// Frontend chat shape; distinct from the SSE AgentMessage wire type.
export type ChatMessageRole = "user" | "assistant" | "system" | "tool";

export type PlannedStepInfo = {
  agent_name: string;
  rationale: string | null;
};

export type ReasoningPayload =
  | { kind: "plan"; summary: string | null; steps: PlannedStepInfo[] }
  | {
      kind: "step";
      index: number;
      total: number;
      agent_name: string;
      rationale: string | null;
    };

// Compact reasoning trail attached to a completed assistant message.
// Saved on backend so reload restores the full thinking process.
export type ToolInvocation = {
  name: string;
  arguments: Record<string, unknown> | null;
  result: string | null;
};

export type AggregatedReasoningStep = {
  agent_name: string;
  rationale: string | null;
  tool_invocations: ToolInvocation[];
};

export type AggregatedReasoning = {
  plan_summary: string | null;
  steps: AggregatedReasoningStep[];
};

export type ChatMessage = {
  id: string;
  role: ChatMessageRole;
  content: string;
  agentName?: string;
  // True for inline "→ Running:" plan separators (not a bubble).
  isStep?: boolean;
  // Intermediate narration ("Planning to run …") — folded into reasoning.
  isProgress?: boolean;
  // Structured reasoning emitted by the orchestrator (plan or per-step rationale).
  reasoning?: ReasoningPayload;
  // Folded reasoning trail attached to the final assistant message.
  aggregatedReasoning?: AggregatedReasoning;
  toolCalls?: ToolCall[];
  toolCallId?: string;
  // Set when reply is a degraded fallback; renders warning variant.
  isError?: boolean;
  // Subkind: "timeout" | "llm_failure" | "empty_reply".
  errorKind?: string;
  citations?: Citation[];
  catalogGrounding?: CatalogGrounding;
  // Structured web-search results — rendered as clickable cards in the
  // bubble so users don't see a plain-text URL dump.
  webSearchResults?: WebSearchResult[];
  webSearchQuery?: string;
  // Set when the orchestrator wants the FE to render a "search the web?" CTA
  // after an empty catalog search. `query` is the original user question.
  confirmWebSearch?: { query: string };
  // Set when a notebook-mode tool agent ran and the FE should auto-open the
  // matching panel (summary / quiz / flashcards) and show the artifact.
  suggestPanel?: {
    panel: "summary" | "quiz" | "flashcards";
    notebookId: string | null;
    autoOpen: boolean;
  };
  // Set when orchestrator detected the user's question fits another mode
  // better; the bubble renders a banner with a "Switch to X" button.
  suggestMode?: {
    targetMode: ChatMode;
    reason: string | null;
  };
  createdAt: string;
};

export type CatalogGroundingRow = {
  name: string;
  object_type: string | null;
  ra_deg: number | null;
  dec_deg: number | null;
};

export type CatalogGroundingWebSource = {
  title: string;
  url: string;
};

export type CatalogGrounding = {
  query: string;
  source: string;
  row_count: number;
  rows: CatalogGroundingRow[];
  web_sources?: CatalogGroundingWebSource[];
};

// Backend emits this on assistant.extra.web_search_results when a
// _rule_web_search hit (general mode "search the web / tìm trên mạng").
export type WebSearchResult = {
  title: string;
  url: string;
  snippet: string;
  source: string | null;
};

// Scrollback cap; persistence is a hot cache, DB is source of truth.
const MAX_MESSAGES = 50;

// True for messages that should be folded into the next assistant answer
// instead of shown as separate bubbles.
function isReasoningFragment(msg: ChatMessage): boolean {
  if (msg.role === "tool") return true;
  if (msg.role === "system" && msg.reasoning) return true;
  if (msg.role === "assistant" && msg.isProgress) return true;
  if (
    msg.role === "assistant" &&
    msg.toolCalls &&
    msg.toolCalls.length > 0 &&
    msg.content.trim().length === 0
  ) {
    return true;
  }
  return false;
}

// Merge an incoming fragment into the in-progress reasoning trail.
function foldReasoning(
  prev: AggregatedReasoning | null,
  msg: ChatMessage,
): AggregatedReasoning {
  const trail: AggregatedReasoning = prev
    ? { plan_summary: prev.plan_summary, steps: prev.steps.map((s) => ({ ...s, tool_invocations: [...s.tool_invocations] })) }
    : { plan_summary: null, steps: [] };

  if (msg.role === "system" && msg.reasoning) {
    if (msg.reasoning.kind === "plan") {
      trail.plan_summary = msg.reasoning.summary;
      // Seed steps from plan so rationales appear before any execution.
      if (trail.steps.length === 0) {
        trail.steps = msg.reasoning.steps.map((s) => ({
          agent_name: s.agent_name,
          rationale: s.rationale,
          tool_invocations: [],
        }));
      }
    } else {
      // Step notice — replace placeholder if planner-seeded, else append.
      const existing = trail.steps[msg.reasoning.index];
      if (existing && existing.agent_name === msg.reasoning.agent_name) {
        existing.rationale = msg.reasoning.rationale ?? existing.rationale;
      } else {
        trail.steps[msg.reasoning.index] = {
          agent_name: msg.reasoning.agent_name,
          rationale: msg.reasoning.rationale,
          tool_invocations: [],
        };
      }
    }
    return trail;
  }

  // Intermediate narration enriches the most recent step's rationale.
  if (msg.role === "assistant" && msg.isProgress && msg.content.trim()) {
    const lastStep = trail.steps[trail.steps.length - 1];
    const target =
      lastStep ?? {
        agent_name: msg.agentName ?? "agent",
        rationale: null,
        tool_invocations: [],
      };
    target.rationale = target.rationale
      ? `${target.rationale}\n\n${msg.content.trim()}`
      : msg.content.trim();
    if (!lastStep) trail.steps.push(target);
    return trail;
  }

  if (msg.role === "assistant" && msg.toolCalls?.length) {
    const lastStep = trail.steps[trail.steps.length - 1];
    const target =
      lastStep ?? { agent_name: msg.agentName ?? "agent", rationale: null, tool_invocations: [] };
    for (const tc of msg.toolCalls) {
      target.tool_invocations.push({
        name: tc.name,
        arguments: tc.arguments ?? null,
        result: null,
      });
    }
    if (!lastStep) trail.steps.push(target);
    return trail;
  }

  if (msg.role === "tool") {
    // Pair with the most recent open invocation; fall back to a synthetic step.
    let attached = false;
    for (let i = trail.steps.length - 1; i >= 0 && !attached; i--) {
      const step = trail.steps[i];
      for (let j = step.tool_invocations.length - 1; j >= 0; j--) {
        const inv = step.tool_invocations[j];
        if (inv.result === null && (!msg.agentName || inv.name === msg.agentName)) {
          inv.result = msg.content;
          attached = true;
          break;
        }
      }
    }
    if (!attached) {
      const lastStep = trail.steps[trail.steps.length - 1];
      const target =
        lastStep ?? { agent_name: "agent", rationale: null, tool_invocations: [] };
      target.tool_invocations.push({
        name: msg.agentName ?? "tool",
        arguments: null,
        result: msg.content,
      });
      if (!lastStep) trail.steps.push(target);
    }
    return trail;
  }

  return trail;
}

// Defensive narrowing for fields loaded from messages.extra (untrusted JSON).

function asString(v: unknown): string | null {
  return typeof v === "string" ? v : null;
}

function asNumber(v: unknown): number {
  return typeof v === "number" ? v : 0;
}

function parseAggregatedReasoning(raw: unknown): AggregatedReasoning | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const r = raw as Record<string, unknown>;
  const stepsRaw = Array.isArray(r.steps) ? r.steps : [];
  const steps: AggregatedReasoningStep[] = [];
  for (const s of stepsRaw) {
    if (!s || typeof s !== "object") continue;
    const obj = s as Record<string, unknown>;
    if (typeof obj.agent_name !== "string") continue;
    const invsRaw = Array.isArray(obj.tool_invocations) ? obj.tool_invocations : [];
    const invs: ToolInvocation[] = [];
    for (const inv of invsRaw) {
      if (!inv || typeof inv !== "object") continue;
      const i = inv as Record<string, unknown>;
      invs.push({
        name: typeof i.name === "string" ? i.name : "tool",
        arguments:
          i.arguments && typeof i.arguments === "object"
            ? (i.arguments as Record<string, unknown>)
            : null,
        result: typeof i.result === "string" ? i.result : null,
      });
    }
    steps.push({
      agent_name: obj.agent_name,
      rationale: asString(obj.rationale),
      tool_invocations: invs,
    });
  }
  if (!steps.length && !r.plan_summary) return undefined;
  return {
    plan_summary: asString(r.plan_summary),
    steps,
  };
}

function parseCitations(raw: unknown): Citation[] | undefined {
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
      score: asNumber(c.score),
    });
  }
  return out.length > 0 ? out : undefined;
}

function parseWebSearchResults(raw: unknown): WebSearchResult[] | undefined {
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

function parseCatalogGrounding(raw: unknown): CatalogGrounding | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const g = raw as Record<string, unknown>;
  if (typeof g.query !== "string" || typeof g.source !== "string") return undefined;
  const rowsRaw = Array.isArray(g.rows) ? g.rows : [];
  const rows: CatalogGroundingRow[] = [];
  for (const r of rowsRaw) {
    if (!r || typeof r !== "object") continue;
    const o = r as Record<string, unknown>;
    if (typeof o.name !== "string") continue;
    rows.push({
      name: o.name,
      object_type: asString(o.object_type),
      ra_deg: typeof o.ra_deg === "number" ? o.ra_deg : null,
      dec_deg: typeof o.dec_deg === "number" ? o.dec_deg : null,
    });
  }
  const websRaw = Array.isArray(g.web_sources) ? g.web_sources : [];
  const webs: CatalogGroundingWebSource[] = [];
  for (const w of websRaw) {
    if (!w || typeof w !== "object") continue;
    const o = w as Record<string, unknown>;
    if (typeof o.title !== "string" || typeof o.url !== "string") continue;
    webs.push({ title: o.title, url: o.url });
  }
  return {
    query: g.query,
    source: g.source,
    row_count: asNumber(g.row_count),
    rows,
    web_sources: webs.length ? webs : undefined,
  };
}

// Tool-rail mode; drives left panel and task_input attachments.
export type ChatMode = "general" | "notebook" | "fits" | "catalog";

// Snapshot used by useChat to ground catalog-mode follow-ups.
export type LastCatalogSearch = {
  query: string;
  source: CatalogSource;
  results: CatalogObject[];
};

// FITS-mode toolbar intent override. Pinning here lets the chat composer
// preface the user's question with a specific routing hint (analyze, report,
// discuss, qa) that the backend FitsAnalystAgent uses instead of sniffing
// the question text. `null` = auto-detect from the question.
export type FitsIntent = "analyze" | "report" | "discuss" | "qa";

type ChatStore = {
  messages: ChatMessage[];
  // Server-minted on first send; null until BE confirms; cleared on clearChat.
  sessionId: string | null;
  notebookId: string | null;
  mode: ChatMode;
  // Mirrors BE session_fits_files join.
  attachedFitsFileIds: string[];
  lastCatalogSearch: LastCatalogSearch | null;
  // FITS-mode toolbar override; null = let backend classify from question text.
  fitsIntent: FitsIntent | null;
  // Mirrors useAgentStream so non-chat surfaces can read without mounting it.
  isStreaming: boolean;
  // Reasoning trail being built for the in-progress assistant turn; null when idle.
  pendingReasoning: AggregatedReasoning | null;
  // True while polling agent_runs after SSE drop.
  isReconnecting: boolean;
  isLoadingSession: boolean;

  setMessages: (messages: ChatMessage[]) => void;
  addMessage: (msg: ChatMessage) => void;
  setNotebookId: (id: string | null) => void;
  setMode: (mode: ChatMode) => void;
  setStreaming: (value: boolean) => void;
  setReconnecting: (value: boolean) => void;
  setLastCatalogSearch: (search: LastCatalogSearch | null) => void;
  setFitsIntent: (intent: FitsIntent | null) => void;
  setAttachedFitsFileIds: (ids: string[]) => void;
  addAttachedFitsFileId: (id: string) => void;
  removeAttachedFitsFileId: (id: string) => void;
  clearChat: () => void;
  // Lazy on first send to avoid orphan rows on empty tabs.
  ensureSessionId: () => Promise<string>;
  // No-op when no session yet; returns updated row or null.
  syncSessionMeta: (patch: {
    mode?: ChatMode;
    notebookId?: string | null;
    title?: string | null;
  }) => Promise<Session | null>;
  loadSession: (sessionId: string) => Promise<Session>;
};

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      messages: [],
      sessionId: null,
      notebookId: null,
      mode: "general",
      attachedFitsFileIds: [],
      isStreaming: false,
      pendingReasoning: null,
      isReconnecting: false,
      isLoadingSession: false,
      lastCatalogSearch: null,
      fitsIntent: null,

      setMessages: (messages) => set({ messages, pendingReasoning: null }),

      addMessage: (msg) =>
        set((state) => {
          // New user turn resets the reasoning bucket for the next response.
          if (msg.role === "user") {
            const next = [...state.messages, msg];
            while (next.length > MAX_MESSAGES) next.shift();
            return { messages: next, pendingReasoning: null };
          }

          // Plan / step / tool / tool-call-only assistant → fold, don't render.
          if (isReasoningFragment(msg)) {
            return {
              pendingReasoning: foldReasoning(state.pendingReasoning, msg),
            };
          }

          // Final assistant answer: attach accumulated trail then push.
          let toPush = msg;
          if (
            msg.role === "assistant" &&
            msg.content.trim().length > 0 &&
            state.pendingReasoning
          ) {
            toPush = { ...msg, aggregatedReasoning: state.pendingReasoning };
          }
          const next = [...state.messages, toPush];
          while (next.length > MAX_MESSAGES) next.shift();
          return { messages: next, pendingReasoning: null };
        }),

      setNotebookId: (id) => set({ notebookId: id }),

      setMode: (mode) => set({ mode }),

      setStreaming: (value) => set({ isStreaming: value }),

      setReconnecting: (value) => set({ isReconnecting: value }),

      setLastCatalogSearch: (search) => set({ lastCatalogSearch: search }),

      setFitsIntent: (intent) => set({ fitsIntent: intent }),

      setAttachedFitsFileIds: (ids) => set({ attachedFitsFileIds: ids }),

      addAttachedFitsFileId: (id) =>
        set((state) =>
          state.attachedFitsFileIds.includes(id)
            ? state
            : { attachedFitsFileIds: [...state.attachedFitsFileIds, id] },
        ),

      removeAttachedFitsFileId: (id) =>
        set((state) => ({
          attachedFitsFileIds: state.attachedFitsFileIds.filter(
            (f) => f !== id,
          ),
        })),

      clearChat: () => {
        // Rotate sessionId; preserve mode but drop per-conversation state.
        set({
          messages: [],
          sessionId: null,
          notebookId: null,
          attachedFitsFileIds: [],
          isStreaming: false,
          pendingReasoning: null,
          isReconnecting: false,
          lastCatalogSearch: null,
          fitsIntent: null,
        });
        // Reset per-conversation FITS pointers; keep user-scoped MRUs.
        const astro = useAstronomyStore.getState();
        astro.selectFile(null);
        astro.setActiveAnalysis(null);
      },

      ensureSessionId: async () => {
        const existing = get().sessionId;
        if (existing) return existing;
        // Mint server-side so messages.session_id FK is valid.
        const { mode, notebookId } = get();
        const session = await sessionService.create({
          mode,
          notebook_id: mode === "notebook" ? notebookId : null,
        });
        set({
          sessionId: session.id,
          attachedFitsFileIds: session.fits_file_ids ?? [],
        });
        return session.id;
      },

      syncSessionMeta: async (patch) => {
        const sessionId = get().sessionId;
        if (!sessionId) return null;
        const body: {
          mode?: ChatMode;
          notebook_id?: string | null;
          title?: string | null;
        } = {};
        if (patch.mode !== undefined) body.mode = patch.mode;
        if (patch.notebookId !== undefined) body.notebook_id = patch.notebookId;
        if (patch.title !== undefined) body.title = patch.title;
        if (Object.keys(body).length === 0) return null;
        try {
          return await sessionService.update(sessionId, body);
        } catch {
          // Stale id (deleted elsewhere); drop so next send mints fresh.
          set({ sessionId: null });
          return null;
        }
      },

      loadSession: async (sessionId) => {
        set({ isLoadingSession: true });
        try {
          const [session, messages] = await Promise.all([
            sessionService.get(sessionId),
            sessionService.getMessages(sessionId),
          ]);
          const mapped: ChatMessage[] = messages.map((m) => {
            const extra = (m.extra ?? {}) as Record<string, unknown>;
            return {
              id: m.id,
              role: m.role,
              content: m.content,
              isError: extra.chat_error === true || undefined,
              errorKind:
                typeof extra.error_kind === "string"
                  ? extra.error_kind
                  : undefined,
              aggregatedReasoning: parseAggregatedReasoning(extra.reasoning),
              citations: parseCitations(extra.citations),
              catalogGrounding: parseCatalogGrounding(extra.catalog_grounding),
              webSearchResults: parseWebSearchResults(extra.web_search_results),
              webSearchQuery:
                typeof extra.web_search_query === "string"
                  ? extra.web_search_query
                  : undefined,
              createdAt: m.created_at,
            };
          });
          set({
            sessionId: session.id,
            notebookId: session.notebook_id ?? null,
            mode: session.mode,
            attachedFitsFileIds: session.fits_file_ids ?? [],
            messages: mapped,
            isStreaming: false,
            pendingReasoning: null,
            isReconnecting: false,
            lastCatalogSearch: null,
          });
          // Reset selection/HDU/active analysis so they don't leak across sessions.
          const attached = session.fits_file_ids ?? [];
          const astro = useAstronomyStore.getState();
          const currentSel = astro.selectedFileId;
          if (currentSel && attached.includes(currentSel)) {
            // Keep current selection.
          } else if (attached.length > 0) {
            astro.selectFile(attached[0]);
          } else {
            astro.selectFile(null);
          }
          astro.setActiveAnalysis(null);
          return session;
        } finally {
          set({ isLoadingSession: false });
        }
      },
    }),
    {
      name: "astrolearn-chat",
      // Streaming flags + lastCatalogSearch are ephemeral; never persist.
      partialize: (state) => ({
        messages: state.messages,
        sessionId: state.sessionId,
        notebookId: state.notebookId,
        mode: state.mode,
        attachedFitsFileIds: state.attachedFitsFileIds,
      }),
    },
  ),
);
