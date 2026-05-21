import { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// RFC 9110 §7.6.1 hop-by-hop + `expect` (undici rejects Expect: 100-continue).
const HOP_BY_HOP = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "content-length",
  "expect",
]);

// Body must be buffered (Node fetch is half-duplex; see whatwg/fetch#1254).
const _DEFAULT_MAX_PROXY_BODY_MB = 100;
const _PARSED_MAX_PROXY_BODY_MB = parseInt(
  process.env.NEXT_PUBLIC_MAX_PROXY_BODY_MB ?? String(_DEFAULT_MAX_PROXY_BODY_MB),
  10,
);
const MAX_PROXY_BODY_BYTES =
  (Number.isFinite(_PARSED_MAX_PROXY_BODY_MB) && _PARSED_MAX_PROXY_BODY_MB > 0
    ? _PARSED_MAX_PROXY_BODY_MB
    : _DEFAULT_MAX_PROXY_BODY_MB) *
  1024 *
  1024;


function _payloadTooLargeResponse(
  declared: number | null,
): Response {
  // Match FastAPI's error envelope for uniform axios extraction.
  return new Response(
    JSON.stringify({
      error: {
        code: "file_too_large",
        message:
          `File exceeds proxy limit. Max: ` +
          `${Math.round(MAX_PROXY_BODY_BYTES / (1024 * 1024))}MB` +
          (declared !== null ? ` (${declared} bytes received)` : "") +
          ".",
        details: {
          limit_bytes: MAX_PROXY_BODY_BYTES,
          declared_bytes: declared,
        },
      },
    }),
    {
      status: 413,
      headers: { "content-type": "application/json" },
    },
  );
}

type Ctx = { params: Promise<{ path: string[] }> };

async function forward(req: NextRequest, ctx: Ctx): Promise<Response> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return new Response(
      JSON.stringify({ error: "NEXT_PUBLIC_API_URL is not configured" }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
  }

  const { path } = await ctx.params;
  const incoming = new URL(req.url);

  // ?token= for EventSource/anchor downloads → Bearer; strip from upstream URL.
  const search = new URLSearchParams(incoming.searchParams);
  const queryToken = search.get("token");
  if (queryToken) search.delete("token");
  const qs = search.toString();
  const upstream = `${apiUrl}/api/v1/${path.join("/")}${qs ? `?${qs}` : ""}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  if (!headers.has("authorization") && queryToken) {
    headers.set("authorization", `Bearer ${queryToken}`);
  }

  const method = req.method.toUpperCase();
  const hasBody = method !== "GET" && method !== "HEAD";

  // Pre-flight size check before allocating the buffer.
  let body: ArrayBuffer | undefined;
  if (hasBody) {
    const declared = req.headers.get("content-length");
    if (declared !== null) {
      const declaredBytes = parseInt(declared, 10);
      if (Number.isFinite(declaredBytes) && declaredBytes > MAX_PROXY_BODY_BYTES) {
        return _payloadTooLargeResponse(declaredBytes);
      }
    }

    body = await req.arrayBuffer();

    // Catches chunked / Content-Length-spoofed bodies.
    if (body.byteLength > MAX_PROXY_BODY_BYTES) {
      return _payloadTooLargeResponse(body.byteLength);
    }
  }

  const init: RequestInit = {
    method,
    headers,
    body,
    cache: "no-store",
    // FastAPI 307s /notebooks → /notebooks/; safe to follow since body is buffered.
    redirect: "follow",
  };

  let upstreamRes: Response;
  try {
    upstreamRes = await fetch(upstream, init);
  } catch (err) {
    return new Response(
      JSON.stringify({
        error: "upstream_unreachable",
        detail: err instanceof Error ? err.message : String(err),
      }),
      { status: 502, headers: { "content-type": "application/json" } },
    );
  }

  const upstreamCt = upstreamRes.headers.get("content-type") ?? "";

  // SSE pass-through with no-buffer hints so proxies don't coalesce frames.
  if (upstreamCt.includes("text/event-stream")) {
    return new Response(upstreamRes.body, {
      status: upstreamRes.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        Connection: "keep-alive",
      },
    });
  }

  // Strip hop-by-hop headers from the response.
  const respHeaders = new Headers();
  upstreamRes.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) respHeaders.set(key, value);
  });

  return new Response(upstreamRes.body, {
    status: upstreamRes.status,
    statusText: upstreamRes.statusText,
    headers: respHeaders,
  });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const PUT = forward;
export const DELETE = forward;
export const OPTIONS = forward;
