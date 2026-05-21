"use client";

import { useCallback, useRef, useState } from "react";

import { agentService } from "@/services/agentService";
import { useAuthStore } from "@/stores/authStore";
import type {
  AgentMessage,
  AgentRunRequest,
  AgentResponse,
  AgentStatus,
} from "@/types/agent.types";


// On SSE drop, poll agent run status then replay terminal output.
const RECONNECT_POLL_MS = 2000;
const RECONNECT_TIMEOUT_MS = 30_000;
const RECONNECT_TERMINAL_STATUSES: ReadonlyArray<AgentStatus> = [
  "succeeded",
  "failed",
  "cancelled",
];

// EventSource is GET-only; our SSE endpoint is POST so we parse fetch's stream.
type ParsedFrame =
  | { type: "message"; data: AgentMessage }
  | { type: "done" }
  | { type: "error"; data: { code?: string; message?: string } };

function parseFrame(frame: string): ParsedFrame | null {
  let event: string | undefined;
  const dataLines: string[] = [];
  for (const line of frame.split("\n")) {
    if (!line) continue;
    if (line.startsWith(":")) continue; // SSE heartbeat
    const idx = line.indexOf(":");
    if (idx === -1) continue;
    const field = line.slice(0, idx).trim();
    let value = line.slice(idx + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }

  const dataStr = dataLines.join("\n");
  if (event === "done") return { type: "done" };
  if (event === "error") {
    let payload: { code?: string; message?: string } = {};
    try {
      payload = dataStr ? JSON.parse(dataStr) : {};
    } catch {
      payload = { message: dataStr || "stream error" };
    }
    return { type: "error", data: payload };
  }
  if (!dataStr) return null;
  try {
    return { type: "message", data: JSON.parse(dataStr) as AgentMessage };
  } catch {
    return null;
  }
}

export type AgentStreamState =
  | "idle"
  | "streaming"
  | "reconnecting"
  | "done"
  | "error";

// Heartbeat frames carry only a progress phase label.
function readHeartbeatPhase(msg: AgentMessage): string | null {
  const extra = msg.extra;
  if (!extra || extra.chat_error) return null;
  if (extra.heartbeat !== true) return null;
  return typeof extra.phase === "string" ? extra.phase : "working";
}

// First SSE frame carries run_id for reconnect correlation; never render it.
function readRunIdFromExtra(msg: AgentMessage): string | null {
  const extra = msg.extra;
  if (!extra) return null;
  const id = extra.run_id;
  return typeof id === "string" && id ? id : null;
}


export function useAgentStream() {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [status, setStatus] = useState<AgentStreamState>("idle");
  const [runStatus, setRunStatus] = useState<AgentStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [streamPhase, setStreamPhase] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const runIdRef = useRef<string | null>(null);
  // Distinguishes user stop from network drop (both throw AbortError).
  const userAbortedRef = useRef<boolean>(false);
  // Cancels any in-flight reconnect poll on overlapping start/stop.
  const reconnectTokenRef = useRef<number>(0);

  const reset = useCallback(() => {
    setMessages([]);
    setStatus("idle");
    setRunStatus(null);
    setError(null);
    setStreamPhase(null);
    runIdRef.current = null;
  }, []);

  const stop = useCallback(() => {
    // Flag before abort so the catch block sees it.
    userAbortedRef.current = true;
    reconnectTokenRef.current += 1;
    controllerRef.current?.abort();
    controllerRef.current = null;
  }, []);

  // Push synthetic assistant turn so user sees output after stream loss.
  const pushReplayMessage = useCallback((run: AgentResponse) => {
    const out = (run.output ?? {}) as Record<string, unknown>;
    const responseText =
      typeof out.response === "string"
        ? out.response
        : typeof out.summary === "string"
          ? out.summary
          : run.status === "failed"
            ? `Run failed: ${run.error ?? "unknown error"}`
            : "Run completed after reconnect.";

    const replay: AgentMessage = {
      id: `reconnect-${run.id}`,
      role: "assistant",
      content: responseText,
      name: null,
      tool_calls: null,
      tool_call_id: null,
      extra: { reconnect_replay: true },
      created_at: run.finished_at ?? new Date().toISOString(),
    };
    setMessages((prev) => [...prev, replay]);
  }, []);

  // Poll agent_runs after SSE drop; bails on token mismatch and timeout.
  const tryReconnect = useCallback(
    async (runId: string): Promise<void> => {
      const myToken = ++reconnectTokenRef.current;
      setStatus("reconnecting");
      setStreamPhase(null);

      const deadline = Date.now() + RECONNECT_TIMEOUT_MS;
      while (Date.now() < deadline) {
        if (myToken !== reconnectTokenRef.current) return; // superseded
        try {
          const snapshot = await agentService.status(runId);
          if (myToken !== reconnectTokenRef.current) return;
          if (RECONNECT_TERMINAL_STATUSES.includes(snapshot.status)) {
            const run = await agentService.get(runId);
            if (myToken !== reconnectTokenRef.current) return;
            pushReplayMessage(run);
            setRunStatus(run.status);
            if (run.status === "succeeded") {
              setStatus("done");
            } else {
              setStatus("error");
              if (run.error) setError(run.error);
            }
            return;
          }
        } catch {
          // Transient — keep polling until the deadline.
        }
        await new Promise((r) => setTimeout(r, RECONNECT_POLL_MS));
      }

      if (myToken !== reconnectTokenRef.current) return;
      setError("Connection lost");
      setStatus("error");
      setRunStatus((s) => s ?? "failed");
    },
    [pushReplayMessage],
  );

  const start = useCallback(
    async (payload: Omit<AgentRunRequest, "stream">) => {
      stop();
      reset();

      userAbortedRef.current = false;

      const controller = new AbortController();
      controllerRef.current = controller;
      setStatus("streaming");
      setRunStatus("running");

      const token = useAuthStore.getState().token;
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      };
      if (token) headers.Authorization = `Bearer ${token}`;

      try {
        const res = await fetch("/api/proxy/agents/run", {
          method: "POST",
          headers,
          body: JSON.stringify({ ...payload, stream: true }),
          signal: controller.signal,
        });

        if (!res.ok) {
          let detail = `HTTP ${res.status}`;
          try {
            const body = await res.json();
            detail =
              (body?.error?.message as string) ||
              (body?.detail as string) ||
              detail;
          } catch {
            // non-JSON body
          }
          throw new Error(detail);
        }

        if (!res.body) throw new Error("No response body");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames separated by blank lines; CRLF normalised.
          let sep: number;
          buffer = buffer.replace(/\r\n/g, "\n");
          while ((sep = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, sep);
            buffer = buffer.slice(sep + 2);
            const parsed = parseFrame(frame);
            if (!parsed) continue;
            if (parsed.type === "message") {
              const runIdFromExtra = readRunIdFromExtra(parsed.data);
              if (runIdFromExtra) {
                runIdRef.current = runIdFromExtra;
                continue;
              }
              const phase = readHeartbeatPhase(parsed.data);
              if (phase !== null) {
                setStreamPhase(phase);
              } else {
                setStreamPhase(null);
                setMessages((prev) => [...prev, parsed.data]);
              }
            } else if (parsed.type === "done") {
              setStatus("done");
              setRunStatus("succeeded");
              return;
            } else if (parsed.type === "error") {
              const msg =
                parsed.data.message ?? parsed.data.code ?? "stream error";
              setError(msg);
              setStatus("error");
              setRunStatus("failed");
              return;
            }
          }
        }

        // Stream closed without `event: done` — treat as success.
        setStatus((s) => (s === "streaming" ? "done" : s));
        setRunStatus((s) => (s === "running" ? "succeeded" : s));
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          if (userAbortedRef.current) {
            setStatus("idle");
            setRunStatus("cancelled");
            return;
          }
          // Network drop — recover via polling.
          const rid = runIdRef.current;
          if (rid) {
            controllerRef.current = null;
            await tryReconnect(rid);
            return;
          }
        }
        const msg = err instanceof Error ? err.message : "stream failed";
        setError(msg);
        setStatus("error");
        setRunStatus("failed");
      } finally {
        controllerRef.current = null;
      }
    },
    [reset, stop, tryReconnect],
  );

  const isStreaming = status === "streaming";
  const isReconnecting = status === "reconnecting";

  return {
    messages,
    status,
    runStatus,
    error,
    isStreaming,
    isReconnecting,
    streamPhase,
    start,
    stop,
    reset,
  };
}
