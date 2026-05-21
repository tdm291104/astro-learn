"use client";

import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import {
  ArrowRight,
  Calendar,
  Database,
  FileText,
  HardDrive,
  Lock,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import type { ReactNode } from "react";

import { StarField } from "@/components/common/StarField";
import { SharedArtifactsSection } from "@/components/notebook/SharedArtifactsSection";
import { SharedDocumentViewerDialog } from "@/components/notebook/SharedDocumentViewerDialog";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/hooks/useT";
import { ROUTES } from "@/lib/constants";
import { formatBytes, formatRelativeTime } from "@/lib/utils";
import { notebookService } from "@/services/notebookService";
import type {
  SharedDocument,
  SharedNotebookResponse,
} from "@/types/notebook.types";

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

export default function SharedNotebookPage() {
  const params = useParams<{ token: string }>();
  const token = params.token;

  const { data, isLoading, error } = useQuery<SharedNotebookResponse>({
    queryKey: ["shared-notebook", token],
    queryFn: () => notebookService.getShared(token),
    enabled: Boolean(token),
    refetchOnWindowFocus: false,
    retry: false,
  });

  return (
    <div className="relative min-h-screen">
      <StarField />
      <div className="relative z-10">
        {isLoading && <LoadingState />}
        {error && <ErrorState error={error} />}
        {data && <Content data={data} token={token} />}
      </div>
    </div>
  );
}

function Content({
  data,
  token,
}: {
  data: SharedNotebookResponse;
  token: string;
}) {
  const totalBytes = data.documents.reduce((sum, d) => sum + d.size_bytes, 0);
  const totalChunks = data.documents.reduce(
    (sum, d) => sum + (d.indexed_chunks ?? 0),
    0,
  );
  const [viewing, setViewing] = useState<SharedDocument | null>(null);

  return (
    <main className="mx-auto max-w-6xl px-5 py-10 sm:px-8 sm:py-14">
      <Hero data={data} />
      <StatsStrip
        docs={data.document_count}
        size={totalBytes}
        chunks={totalChunks}
        updated={data.updated_at}
      />
      <DocumentsGrid documents={data.documents} onOpen={setViewing} />
      <SharedArtifactsSection token={token} />
      <SignUpCta />
      <Footer />

      <SharedDocumentViewerDialog
        token={token}
        documentId={viewing?.document_id ?? null}
        filename={viewing?.filename ?? ""}
        sizeBytes={viewing?.size_bytes ?? 0}
        onClose={() => setViewing(null)}
      />
    </main>
  );
}

function Hero({ data }: { data: SharedNotebookResponse }) {
  const { t } = useT();
  return (
    <header className="relative overflow-hidden rounded-2xl border p-8 sm:p-12"
      style={{
        borderColor: "rgba(226,201,126,0.18)",
        background:
          "linear-gradient(135deg, rgba(226,201,126,0.08) 0%, rgba(110,170,240,0.05) 50%, transparent 100%)",
      }}
    >
      <div className="relative z-10 space-y-5">
        <div
          className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5"
          style={{
            borderColor: "rgba(226,201,126,0.32)",
            background: "rgba(226,201,126,0.08)",
            color: "var(--accent-gold)",
          }}
        >
          <Sparkles className="h-3 w-3" />
          <span
            className="font-orbitron text-[10px] uppercase"
            style={{ letterSpacing: "0.22em" }}
          >
            {t("share.badge")}
          </span>
        </div>

        <h1
          className="font-orbitron text-3xl font-bold uppercase leading-tight sm:text-4xl lg:text-5xl"
          style={{
            color: "var(--text-primary)",
            letterSpacing: "0.08em",
          }}
        >
          {data.title.split(" ").map((word, i, arr) => (
            <span key={i}>
              {i === arr.length - 1 ? (
                <span style={{ color: "var(--accent-gold)" }}>{word}</span>
              ) : (
                word
              )}
              {i < arr.length - 1 && " "}
            </span>
          ))}
        </h1>

        {data.description ? (
          <p
            className="font-exo2 max-w-2xl text-base leading-relaxed sm:text-lg"
            style={{ color: "var(--text-secondary)" }}
          >
            {data.description}
          </p>
        ) : (
          <p
            className="font-exo2 max-w-2xl text-base italic"
            style={{ color: "var(--text-muted)" }}
          >
            {t("share.noDescription")}
          </p>
        )}

        <p
          className="font-space-mono inline-flex items-center gap-2 text-[11px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.18em" }}
        >
          <Calendar className="h-3 w-3" />
          Created {fmtDate(data.created_at)} · Updated{" "}
          {formatRelativeTime(data.updated_at)}
        </p>
      </div>

      {/* Decorative orbital ring in corner */}
      <div
        aria-hidden
        className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full border opacity-40"
        style={{ borderColor: "rgba(226,201,126,0.18)" }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -right-32 -top-32 h-96 w-96 rounded-full border opacity-20"
        style={{ borderColor: "rgba(110,170,240,0.22)" }}
      />
    </header>
  );
}

function StatsStrip({
  docs,
  size,
  chunks,
  updated,
}: {
  docs: number;
  size: number;
  chunks: number;
  updated: string;
}) {
  return (
    <section className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCard
        icon={<FileText className="h-4 w-4" />}
        label="Documents"
        value={String(docs)}
      />
      <StatCard
        icon={<HardDrive className="h-4 w-4" />}
        label="Total Size"
        value={formatBytes(size)}
      />
      <StatCard
        icon={<Database className="h-4 w-4" />}
        label="Chunks"
        value={chunks.toLocaleString()}
      />
      <StatCard
        icon={<Calendar className="h-4 w-4" />}
        label="Updated"
        value={formatRelativeTime(updated)}
      />
    </section>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="cosmic-card relative overflow-hidden p-4">
      <span
        aria-hidden
        className="pointer-events-none absolute right-3 top-3 opacity-30"
        style={{ color: "var(--accent-gold)" }}
      >
        {icon}
      </span>
      <div className="cosmic-stat-label">{label}</div>
      <div
        className="cosmic-stat-value mt-1"
        style={{ color: "var(--text-primary)" }}
      >
        {value}
      </div>
    </div>
  );
}

function DocumentsGrid({
  documents,
  onOpen,
}: {
  documents: SharedDocument[];
  onOpen: (doc: SharedDocument) => void;
}) {
  const { t } = useT();
  return (
    <section className="mt-10">
      <div className="mb-4 flex items-baseline justify-between">
        <h2
          className="font-orbitron text-sm font-semibold uppercase"
          style={{ color: "var(--text-primary)", letterSpacing: "0.18em" }}
        >
          {t("share.documentsLabel")}
        </h2>
        <span
          className="font-space-mono text-[11px] uppercase"
          style={{ color: "var(--text-muted)", letterSpacing: "0.16em" }}
        >
          {documents.length === 1
            ? t("share.itemsCountOne", { n: documents.length })
            : t("share.itemsCount", { n: documents.length })}
        </span>
      </div>

      {documents.length === 0 ? (
        <div
          className="font-exo2 rounded-2xl border-2 border-dashed py-12 text-center text-sm"
          style={{
            borderColor: "rgba(226,201,126,0.18)",
            color: "var(--text-muted)",
          }}
        >
          {t("share.noDocuments")}
        </div>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {documents.map((doc) => (
            <DocumentCard
              key={doc.document_id}
              doc={doc}
              onOpen={() => onOpen(doc)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function DocumentCard({
  doc,
  onOpen,
}: {
  doc: SharedDocument;
  onOpen: () => void;
}) {
  const { t } = useT();
  const ext = doc.filename.split(".").pop()?.toUpperCase() ?? "FILE";
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="cosmic-card cosmic-card-hover group flex w-full items-start gap-3 p-4 text-left transition-transform hover:scale-[1.01]"
        aria-label={`Open ${doc.filename}`}
      >
        <div
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
          style={{
            background: "rgba(110,170,240,0.10)",
            border: "1px solid rgba(110,170,240,0.22)",
          }}
        >
          <FileText
            className="h-4 w-4"
            style={{ color: "var(--accent-blue)" }}
          />
        </div>
        <div className="min-w-0 flex-1">
          <p
            className="font-exo2 truncate text-sm font-medium"
            style={{ color: "var(--text-primary)" }}
            title={doc.filename}
          >
            {doc.filename}
          </p>
          <p
            className="font-space-mono mt-1 text-[10px] uppercase"
            style={{ color: "var(--text-muted)", letterSpacing: "0.14em" }}
          >
            {ext} · {formatBytes(doc.size_bytes)}
          </p>
          {doc.indexed_chunks != null && (
            <p
              className="font-space-mono mt-2 inline-flex items-center gap-1 text-[10px] uppercase"
              style={{
                color: "var(--accent-gold)",
                letterSpacing: "0.14em",
              }}
            >
              <span
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ background: "var(--accent-gold)" }}
                aria-hidden
              />
              {t("share.chunksIndexed", { n: doc.indexed_chunks })}
            </p>
          )}
        </div>
        <ArrowRight
          className="h-3.5 w-3.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
          style={{ color: "var(--accent-gold)" }}
          aria-hidden
        />
      </button>
    </li>
  );
}

function SignUpCta() {
  const { t } = useT();
  return (
    <section
      className="relative mt-10 overflow-hidden rounded-2xl border p-6 text-center sm:p-8"
      style={{
        borderColor: "rgba(226,201,126,0.22)",
        background:
          "linear-gradient(120deg, rgba(226,201,126,0.06) 0%, rgba(110,170,240,0.05) 100%)",
      }}
    >
      <h3
        className="font-orbitron text-base font-semibold uppercase sm:text-lg"
        style={{ color: "var(--text-primary)", letterSpacing: "0.16em" }}
      >
        {t("share.cta.title")}
      </h3>
      <p
        className="font-exo2 mx-auto mt-2 max-w-lg text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        {t("share.cta.description")}
      </p>
      <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
        <Link
          href={ROUTES.register}
          className="cosmic-btn-primary inline-flex items-center gap-2"
        >
          {t("share.cta.signup")} <ArrowRight className="h-3.5 w-3.5" />
        </Link>
        <Link href={ROUTES.login} className="cosmic-btn-ghost">
          {t("share.cta.signin")}
        </Link>
      </div>
    </section>
  );
}

function Footer() {
  const { t } = useT();
  return (
    <footer className="mt-10 flex flex-col items-center gap-2 py-6">
      <p
        className="font-space-mono text-[10px] uppercase"
        style={{ color: "var(--text-muted)", letterSpacing: "0.22em" }}
      >
        {t("share.footer.poweredBy")}
        <span
          className="font-orbitron ml-2 font-semibold"
          style={{ color: "var(--accent-gold)", letterSpacing: "0.18em" }}
        >
          {t("app.name")}
        </span>
      </p>
      <p
        className="font-exo2 text-[11px]"
        style={{ color: "var(--text-muted)" }}
      >
        {t("share.footer.notice")}
      </p>
    </footer>
  );
}

function LoadingState() {
  return (
    <div className="mx-auto max-w-6xl space-y-4 px-5 py-10 sm:px-8 sm:py-14">
      <Skeleton className="h-48 w-full rounded-2xl" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-20 w-full rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-2xl" />
        ))}
      </div>
    </div>
  );
}

function ErrorState({ error }: { error: unknown }) {
  const { t } = useT();
  const status =
    error instanceof AxiosError ? error.response?.status : undefined;
  const isMissing = status === 404;
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-5 py-10 text-center">
      <div
        className="flex h-16 w-16 items-center justify-center rounded-full"
        style={{
          background: isMissing
            ? "rgba(226,201,126,0.10)"
            : "rgba(255,112,67,0.12)",
          border: `1px solid ${isMissing ? "rgba(226,201,126,0.32)" : "rgba(255,112,67,0.32)"}`,
        }}
      >
        <Lock
          className="h-6 w-6"
          style={{
            color: isMissing ? "var(--accent-gold)" : "var(--accent-coral)",
          }}
        />
      </div>
      <h1
        className="font-orbitron mt-5 text-lg font-semibold uppercase"
        style={{ color: "var(--text-primary)", letterSpacing: "0.18em" }}
      >
        {isMissing ? t("share.error.notFound") : t("share.error.generic")}
      </h1>
      <p
        className="font-exo2 mt-3 text-sm"
        style={{ color: "var(--text-secondary)" }}
      >
        {isMissing
          ? t("share.error.notFoundDesc")
          : t("share.error.genericDesc")}
      </p>
      <Link
        href={ROUTES.home}
        className="cosmic-btn-ghost mt-6 inline-flex items-center gap-2"
      >
        {t("share.error.back")} <ArrowRight className="h-3.5 w-3.5" />
      </Link>
    </div>
  );
}
