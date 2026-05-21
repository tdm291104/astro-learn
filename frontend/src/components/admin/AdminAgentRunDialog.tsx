"use client";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminAgentRun } from "@/hooks/useAdmin";

// Read-only modal of task_input + output for debugging agent failures.
export function AdminAgentRunDialog({
  runId,
  open,
  onOpenChange,
}: {
  runId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { data, isLoading } = useAdminAgentRun(open ? runId : null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>
            <span
              className="font-orbitron uppercase"
              style={{ letterSpacing: "0.16em" }}
            >
              Agent Run
            </span>
          </DialogTitle>
          <DialogDescription>
            <span
              className="font-space-mono text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              {data?.run.agent_name ?? "—"} · {data?.run.status ?? ""}
            </span>
          </DialogDescription>
        </DialogHeader>

        {isLoading || !data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="space-y-4">
            {data.run.error && (
              <div
                className="rounded-md p-3"
                style={{
                  background: "rgba(220, 90, 90, 0.08)",
                  border: "1px solid rgba(220, 90, 90, 0.3)",
                }}
              >
                <p
                  className="font-orbitron text-[10px] uppercase"
                  style={{
                    color: "var(--accent-coral)",
                    letterSpacing: "0.16em",
                  }}
                >
                  Error
                </p>
                <pre
                  className="font-space-mono mt-1 max-h-40 overflow-auto text-xs"
                  style={{
                    color: "var(--accent-coral)",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {data.run.error}
                </pre>
              </div>
            )}

            <PayloadBlock label="Task Input" value={data.task_input} />
            <PayloadBlock label="Output" value={data.output} />

            <dl
              className="font-space-mono grid grid-cols-2 gap-2 text-[11px]"
              style={{ color: "var(--text-secondary)" }}
            >
              <Row label="User">{data.run.user_email ?? "—"}</Row>
              <Row label="Status">{data.run.status}</Row>
              <Row label="Duration">
                {data.run.duration_ms !== null
                  ? `${(data.run.duration_ms / 1000).toFixed(2)}s`
                  : "—"}
              </Row>
              <Row label="Started">
                {data.run.started_at ? data.run.started_at.replace("T", " ") : "—"}
              </Row>
            </dl>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function PayloadBlock({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  return (
    <div>
      <p
        className="font-orbitron text-[10px] uppercase"
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.16em",
        }}
      >
        {label}
      </p>
      <pre
        className="font-space-mono mt-1 max-h-48 overflow-auto rounded-md p-3 text-[11px]"
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid var(--border)",
          color: "var(--text-primary)",
          whiteSpace: "pre-wrap",
        }}
      >
        {value === null || value === undefined
          ? "—"
          : JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}

function Row({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt
        style={{
          color: "var(--text-muted)",
          letterSpacing: "0.12em",
        }}
      >
        {label}
      </dt>
      <dd
        className="mt-0.5"
        style={{ color: "var(--text-primary)" }}
      >
        {children}
      </dd>
    </div>
  );
}
