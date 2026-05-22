"""Question-answering over indexed documents (NotebookLM-style)."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any, ClassVar, Final

from agents.base.agent_message import AgentMessage
from agents.base.agent_registry import AgentRegistry
from agents.base.agent_state import AgentState
from agents.base.base_agent import BaseAgent
from core.config import get_settings
from core.exceptions import AgentError
from core.llm.prompt_templates import QA_FROM_CONTEXT, language_directive, render

# Context cap; full chunk available via citations.
_CONTEXT_SNIPPET_CHAR_CAP: int = 300

_CITATION_SNIPPET_CHAR_CAP: int = 300

_REFUSAL_TEXT: str = "I cannot answer from the provided documents."


# --- Metadata intent detection ---------------------------------------------
#
# Structural questions (counts, file names, page lookups) must bypass vector
# search — semantic retrieval can't accurately answer "how many docs" because
# it returns top-k chunks rather than a row count. The regex catches the
# common shapes in EN + VN; ambiguous cases fall through to RAG so the user
# doesn't get refused on a legitimate content question.


_METADATA_INTENT_PATTERNS: Final[list[tuple[str, re.Pattern[str]]]] = [
    # Page lookup: "page 3 says what" / "trang 5 nói gì" — checked first
    # because page numbers are unambiguous.
    (
        "document_page",
        re.compile(
            r"\b(?:page|trang)\s*(\d+)\b"
            r"|trang\s+s[ốo]\s+(\d+)",
            re.IGNORECASE,
        ),
    ),
    # "docs tên X có nội dung gì" / "what is in document X.pdf"
    # Negative lookahead skips the list-shape "tài liệu tên là gì" so it
    # doesn't swallow what the user meant as "give me the names".
    (
        "find_document",
        re.compile(
            r"(?:docs?|tài\s*li[ệe]u|file)\s+(?:t[êe]n|named|called)\s+"
            r"(?!l[àa]\s+g[ìi]|gì\b|what\b)"
            r"|(?:n[ộo]i\s+dung|contents?\s+of)\s+(?:c[ủu]a\s+)?(?:docs?|tài\s*li[ệe]u|file)",
            re.IGNORECASE,
        ),
    ),
    # "file mới nhất / latest doc"
    (
        "latest_document",
        re.compile(
            r"\b(?:latest|newest|most\s+recent|last\s+upload)\b"
            r"|(?:m[ớo]i\s+(?:nh[ấa]t|upload|t[ảa]i\s+l[êe]n)|g[ầa]n\s+đ[âa]y\s+nh[ấa]t)"
            r"|m[ớo]i\s+(?:upload|t[ảa]i\s+l[êe]n)",
            re.IGNORECASE,
        ),
    ),
    # "how many docs" / "(có) bao nhiêu tài liệu" / "đã upload bao nhiêu"
    # `có` is optional so "notebook cái bao nhiêu tài liệu" still matches.
    (
        "count_documents",
        re.compile(
            r"\b(?:how\s+many|total\s+(?:number\s+of)?)\s+"
            r"(?:docs?|documents?|files?|tài\s*li[ệe]u|pdfs?)"
            r"|bao\s+nhi[êe]u\s+(?:docs?|tài\s*li[ệe]u|file|pdfs?)"
            r"|đ[ãa]\s+upload\s+(?:bao\s+nhi[êe]u|đư[ợo]c\s+m[ấa]y)"
            r"|s[ốo]\s+l[ưu][ợo]ng\s+(?:docs?|tài\s*li[ệe]u|file)",
            re.IGNORECASE,
        ),
    ),
    # "how many notebooks" / "có bao nhiêu notebooks"
    (
        "count_notebooks",
        re.compile(
            r"\b(?:how\s+many|total\s+number\s+of)\s+notebooks?\b"
            r"|bao\s+nhi[êe]u\s+notebooks?"
            r"|đ[ãa]\s+t[ạa]o\s+bao\s+nhi[êe]u\s+notebooks?",
            re.IGNORECASE,
        ),
    ),
    # "danh sách / liệt kê / list / show / tên các tài liệu"
    (
        "list_documents",
        re.compile(
            r"\b(?:list|show\s+(?:me\s+)?(?:all\s+)?|name(?:s)?\s+of)\s+"
            r"(?:the\s+|all\s+)?(?:docs?|documents?|files?|pdfs?)"
            r"|li[ệe]t\s+k[êe]\s+(?:các\s+)?(?:docs?|tài\s*li[ệe]u|file)"
            r"|danh\s+s[áa]ch\s+(?:các\s+)?(?:docs?|tài\s*li[ệe]u|file)"
            r"|c[óo]\s+nh[ữu]ng\s+(?:docs?|tài\s*li[ệe]u|file)\s+(?:n[àa]o|gì)"
            # "(các/những)? (docs|tài liệu|file) tên (là)? gì" — asking for
            # the names rather than naming a specific doc.
            r"|(?:docs?|tài\s*li[ệe]u|file)\s+t[êe]n\s+(?:l[àa]\s+)?gì"
            r"|t[êe]n\s+(?:các\s+)?(?:docs?|tài\s*li[ệe]u|file)",
            re.IGNORECASE,
        ),
    ),
    # "notebook này tên gì / tell me about this notebook"
    (
        "notebook_info",
        re.compile(
            r"\b(?:about\s+this\s+notebook|notebook\s+(?:title|name|info))\b"
            r"|notebook\s+n[àa]y\s+t[êe]n\s+gì"
            r"|t[êe]n\s+c[ủu]a\s+notebook\s+n[àa]y"
            r"|notebook\s+n[àa]y\s+l[àa]\s+gì",
            re.IGNORECASE,
        ),
    ),
]


def _filename_from_question(question: str) -> str | None:
    """Extract a document filename hint from the user question.

    Order matters — try the unambiguous shapes first so we don't truncate
    a filename like "2605.04220v1.pdf" at the first dot:
      - quoted filename: `"my-paper.pdf"` / `'foo bar'`
      - bare token with a known doc extension: `... 2605.04220v1.pdf ...`
      - "của X" / "of X" — Vietnamese genitive picks up arxiv-like tokens
      - after a `tên|named|called` marker (extensionless fallback)

    Returns `None` for vague references like "trang 2"; the handler then
    consults the notebook's doc list and either auto-resolves (1 doc) or
    asks the user to specify (many docs).
    """
    quoted = re.search(r"[\"']([^\"']{2,200})[\"']", question)
    if quoted:
        return quoted.group(1).strip()
    ext_token = re.search(
        r"([\w\-]+(?:\.[\w\-]+)*\.(?:pdf|txt|md|docx?|html?|csv|json))",
        question,
        re.IGNORECASE,
    )
    if ext_token:
        return ext_token.group(1)
    # "của 2605.04220v1" / "of 2605.04220v1" — arxiv-style tokens are
    # >=4 chars and contain at least one digit so we don't accidentally
    # grab pronouns like "của tôi" / "of mine".
    genitive = re.search(
        r"(?:c[ủu]a|of)\s+([\w\-.]{4,80})",
        question,
        re.IGNORECASE,
    )
    if genitive:
        candidate = genitive.group(1).rstrip(".,?!")
        if any(c.isdigit() for c in candidate) and len(candidate) >= 4:
            return candidate
    marker = re.search(
        r"(?:t[êe]n|named|called)\s+([^\s,?!]+(?:\s+[^\s,?!]+){0,4})",
        question,
        re.IGNORECASE,
    )
    if marker:
        return marker.group(1).strip().strip(".,?!")
    return None


def _classify_metadata_intent(question: str) -> tuple[str, dict[str, Any]] | None:
    """Return (intent_name, args) if question shape matches; else None."""
    for intent_name, pattern in _METADATA_INTENT_PATTERNS:
        m = pattern.search(question)
        if not m:
            continue
        args: dict[str, Any] = {}
        if intent_name == "document_page":
            # Two capture groups for two shapes; first non-None wins.
            page_str = next((g for g in m.groups() if g), None)
            if page_str:
                try:
                    args["page"] = int(page_str)
                except ValueError:
                    continue
            name = _filename_from_question(question)
            if name:
                args["name_like"] = name
            # Need both for document_page; without filename fall through to
            # generic content lookup (find_document semantics).
            if "page" not in args:
                continue
        if intent_name in {"find_document", "document_page"}:
            name = _filename_from_question(question)
            if name and "name_like" not in args:
                args["name_like"] = name
        # find_document only makes sense with a filename to match. Without
        # one, defer to a later pattern (e.g. list_documents) — otherwise
        # we'd reject the call at the tool's input validation.
        if intent_name == "find_document" and not args.get("name_like"):
            continue
        return intent_name, args
    return None


@AgentRegistry.register
class QAAgent(BaseAgent):
    """Answer a question grounded in indexed documents."""

    name: ClassVar[str] = "qa"
    description: ClassVar[str] = (
        "Answer a question using only the documents indexed for the given "
        "notebook. Returns citations pointing at the source chunks."
    )
    capabilities: ClassVar[list[str]] = ["rag", "citations", "refusal_when_unsure"]

    async def run(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AgentState:
        state = state or AgentState(agent_name=self.name)
        async for _ in self._iter(task, state):
            pass
        return state

    async def stream(
        self,
        task: dict[str, Any],
        *,
        state: AgentState | None = None,
    ) -> AsyncIterator[AgentMessage]:
        state = state or AgentState(agent_name=self.name)
        async for message in self._iter(task, state):
            yield message

    async def _iter(
        self,
        task: dict[str, Any],
        state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        question = self._require_question(task)
        notebook_id = self._coerce_notebook_id(task)
        top_k = int(task.get("top_k", 5))
        language = task.get("language") or task.get("locale")

        user_msg = AgentMessage(role="user", content=question)
        state.append(user_msg)
        yield user_msg

        # Metadata intent first — RAG can't accurately answer "how many docs",
        # "what files do I have", or "page N says what" because semantic
        # retrieval doesn't expose structural counts or page indexes.
        intent = _classify_metadata_intent(question)
        if intent is not None:
            metadata_tool = self.get_tool("notebook_metadata")
            if metadata_tool is not None:
                async for msg in self._handle_metadata(
                    question=question,
                    intent_name=intent[0],
                    intent_args=intent[1],
                    notebook_id=notebook_id,
                    owner_id=state.user_id,
                    language=language,
                    state=state,
                ):
                    yield msg
                return
            # No tool wired (e.g. test factory without DB) → fall through to RAG.

        tool = self.get_tool("vector_search")
        if tool is None:
            raise AgentError(
                message="QAAgent requires the 'vector_search' tool",
                code="missing_tool",
                details={"required": "vector_search"},
            )
        # Two-stage retrieval: pull a wider candidate pool, then cross-encoder
        # rerank to top_k. Reranker is the single biggest precision lever per
        # the retrieval evaluation (hit@1 0.25 -> 0.63, MRR 0.48 -> 0.68).
        candidate_multiplier = max(
            1, int(task.get("rerank_candidates_mult") or get_settings().RERANK_CANDIDATE_MULTIPLIER)
        )
        wide_top_k = min(top_k * candidate_multiplier, 20)  # VectorSearchInput caps top_k at 20
        candidates: list[dict[str, Any]] = await tool(
            mode="search",
            query=question,
            notebook_id=notebook_id,
            top_k=wide_top_k,
        )
        matches = await self._rerank(question, candidates, top_n=top_k)

        tool_msg = AgentMessage(
            role="tool",
            name="vector_search",
            content=json.dumps(matches),
        )
        state.append(tool_msg)
        yield tool_msg

        if not matches:
            refusal = AgentMessage(role="assistant", content=_REFUSAL_TEXT)
            state.append(refusal)
            yield refusal
            state.final_output = {"answer": _REFUSAL_TEXT, "citations": []}
            return

        context = _build_numbered_context(matches)
        system_prompt = render(QA_FROM_CONTEXT, context=context)

        # Low temp: grounded over creative.
        answer = await self.llm.complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.2,
        )
        answer = (answer or "").strip() or _REFUSAL_TEXT

        citations = [_match_to_citation(m) for m in matches]
        assistant_msg = AgentMessage(
            role="assistant",
            content=answer,
            # Citations on extra so FE chat bubble can render source chips.
            extra={"citations": citations},
        )
        state.append(assistant_msg)
        yield assistant_msg

        state.final_output = {"answer": answer, "citations": citations}

    async def _handle_metadata(
        self,
        *,
        question: str,
        intent_name: str,
        intent_args: dict[str, Any],
        notebook_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        language: str | None,
        state: AgentState,
    ) -> AsyncIterator[AgentMessage]:
        """Dispatch metadata intent to the notebook_metadata tool, then
        synthesise a natural-language answer via the LLM."""
        tool = self.get_tool("notebook_metadata")
        assert tool is not None  # caller already checked

        tool_args: dict[str, Any] = {
            "operation": intent_name,
            "notebook_id": notebook_id,
        }
        # Owner-scope queries only run when state carries the owner.
        if intent_name == "count_notebooks":
            if owner_id is None:
                yield self._cannot_answer_without_owner(state, language)
                return
            tool_args = {"operation": "count_notebooks", "owner_id": owner_id}
        elif intent_name in {"latest_document", "count_documents"}:
            # Default to notebook scope; overridable by adding "across all
            # notebooks" / "tất cả notebooks" intent later.
            if owner_id is not None:
                tool_args["owner_id"] = owner_id
        tool_args.update(intent_args)

        # `trang 2` with no filename is the common ask when the notebook
        # holds a single paper. Resolve the implicit document here so the
        # tool's name_like requirement doesn't crash the call. When multiple
        # docs exist, surface a clarification rather than picking blind.
        if intent_name == "document_page" and not tool_args.get("name_like"):
            try:
                listing = await tool(
                    operation="list_documents",
                    notebook_id=notebook_id,
                    limit=20,
                )
            except Exception:  # noqa: BLE001
                listing = {"documents": []}
            docs = listing.get("documents") or []
            if len(docs) == 1:
                tool_args["name_like"] = docs[0]["filename"]
            elif len(docs) > 1:
                names = ", ".join(d.get("filename", "?") for d in docs[:5])
                vi = (language or "").lower() == "vi"
                ask = (
                    f"Notebook này có nhiều tài liệu ({names}). "
                    "Bạn muốn xem trang đó của file nào? "
                    "Hãy nhắc lại kèm tên file giúp em nhé."
                    if vi
                    else
                    f"This notebook has multiple documents ({names}). "
                    "Which file's page do you mean? Please re-ask with "
                    "the filename."
                )
                msg = AgentMessage(
                    role="assistant",
                    content=ask,
                    extra={
                        "metadata_query": True,
                        "operation": intent_name,
                        "needs_filename": True,
                    },
                )
                state.append(msg)
                yield msg
                state.final_output = {"answer": ask, "citations": []}
                return
            # 0 docs falls through to the tool which will surface "empty".

        try:
            result = await tool(**tool_args)
        except Exception as exc:  # noqa: BLE001 — surface as a graceful refusal
            err_msg = AgentMessage(
                role="assistant",
                content=_metadata_error_text(language, str(exc)),
            )
            state.append(err_msg)
            yield err_msg
            state.final_output = {"answer": err_msg.content, "citations": []}
            return

        tool_msg = AgentMessage(
            role="tool",
            name="notebook_metadata",
            content=json.dumps(result, default=str),
        )
        state.append(tool_msg)
        yield tool_msg

        answer = await self._synthesise_metadata_answer(
            question=question,
            tool_result=result,
            language=language,
        )

        # Page content path doubles as a citation source for the FE.
        citations = _metadata_citations(intent_name, result)
        extra: dict[str, Any] = {"metadata_query": True, "operation": intent_name}
        if citations:
            extra["citations"] = citations
        assistant_msg = AgentMessage(
            role="assistant",
            content=answer,
            extra=extra,
        )
        state.append(assistant_msg)
        yield assistant_msg
        state.final_output = {
            "answer": answer,
            "citations": citations,
            "metadata": result,
        }

    async def _synthesise_metadata_answer(
        self,
        *,
        question: str,
        tool_result: dict[str, Any],
        language: str | None,
    ) -> str:
        """Turn the structured tool result into a conversational reply."""
        # Compact JSON keeps the prompt tight while preserving all fields the
        # LLM might want to surface (filenames, dates, counts, chunks).
        system_prompt = (
            "You are answering a question about the user's notebooks/files "
            "using ONLY the structured result of a metadata lookup. "
            "State the relevant fields plainly — do not invent counts, "
            "filenames, dates, or content that aren't in the result. "
            "If the result is empty or null, say so honestly."
        )
        lang_clause = language_directive(language)
        if lang_clause:
            system_prompt = f"{system_prompt}\n\n{lang_clause}"
        user_prompt = (
            f"User question: {question}\n\n"
            f"Tool result (JSON):\n{json.dumps(tool_result, default=str, ensure_ascii=False)}\n\n"
            "Reply in 1-3 short sentences. Include concrete numbers and "
            "filenames from the result when relevant."
        )
        try:
            raw = await self.llm.complete(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
        except Exception:  # noqa: BLE001 — fall back to a deterministic render
            return _format_metadata_fallback(tool_result, language)
        text = (raw or "").strip()
        return text or _format_metadata_fallback(tool_result, language)

    @staticmethod
    def _cannot_answer_without_owner(
        state: AgentState, language: str | None
    ) -> AgentMessage:
        text = (
            "Em chưa nhận diện được tài khoản, không trả lời được câu này."
            if (language or "").lower() == "vi"
            else "I couldn't identify your account to answer that."
        )
        msg = AgentMessage(role="assistant", content=text)
        state.append(msg)
        state.final_output = {"answer": text, "citations": []}
        return msg

    async def _rerank(
        self,
        question: str,
        candidates: list[dict[str, Any]],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Cross-encoder rerank; on failure, fall back to vector-score order."""
        if len(candidates) <= top_n:
            return candidates
        try:
            ranked = await self.llm.rerank(
                question,
                [str(c.get("text") or "") for c in candidates],
                top_n=top_n,
            )
        except Exception:
            # Reranker is best-effort; vector ordering still works.
            return candidates[:top_n]
        out: list[dict[str, Any]] = []
        for idx, score in ranked:
            if 0 <= idx < len(candidates):
                hit = dict(candidates[idx])
                hit["score"] = score
                out.append(hit)
        return out

    @staticmethod
    def _require_question(task: dict[str, Any]) -> str:
        question = task.get("question")
        if not isinstance(question, str) or not question.strip():
            raise AgentError(
                message="QAAgent requires task['question'] (non-empty str)",
                code="invalid_task",
            )
        return question.strip()

    @staticmethod
    def _coerce_notebook_id(task: dict[str, Any]) -> uuid.UUID:
        raw = task.get("notebook_id")
        if raw is None:
            raise AgentError(
                message="QAAgent requires task['notebook_id']",
                code="invalid_task",
            )
        if isinstance(raw, uuid.UUID):
            return raw
        try:
            return uuid.UUID(str(raw))
        except (ValueError, TypeError) as exc:
            raise AgentError(
                message=f"Invalid notebook_id: {raw!r}",
                code="invalid_task",
            ) from exc


def _metadata_citations(
    intent_name: str, result: dict[str, Any]
) -> list[dict[str, Any]]:
    """Citations only for page-content lookups; other ops are pure metadata."""
    if intent_name != "document_page":
        return []
    chunks = result.get("chunks") or []
    document = result.get("document") or {}
    document_id = document.get("id") or ""
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        if len(text) > _CITATION_SNIPPET_CHAR_CAP:
            text = text[:_CITATION_SNIPPET_CHAR_CAP].rstrip() + "..."
        out.append({
            "document_id": document_id,
            "chunk_id": str(chunk.get("chunk_id") or ""),
            "snippet": text,
            "score": 1.0,
            "page": chunk.get("page"),
        })
    return out


def _format_metadata_fallback(result: dict[str, Any], language: str | None) -> str:
    """Deterministic answer when the LLM synth step fails."""
    op = result.get("operation")
    vi = (language or "").lower() == "vi"
    if op == "count_notebooks":
        n = result.get("count", 0)
        return f"Bạn có {n} notebook." if vi else f"You have {n} notebook(s)."
    if op == "count_documents":
        n = result.get("count", 0)
        scope = result.get("scope")
        if vi:
            where = "trong notebook này" if scope == "notebook" else "tổng cộng"
            return f"Bạn có {n} tài liệu {where}."
        where = "in this notebook" if scope == "notebook" else "in total"
        return f"You have {n} document(s) {where}."
    if op == "list_documents":
        docs = result.get("documents") or []
        names = ", ".join(d.get("filename", "?") for d in docs[:5])
        more = f" (+{len(docs) - 5})" if len(docs) > 5 else ""
        return (f"Tài liệu: {names}{more}." if vi else f"Documents: {names}{more}.")
    if op == "latest_document":
        doc = result.get("document")
        if not doc:
            return ("Chưa có tài liệu nào." if vi else "No documents yet.")
        name = doc.get("filename", "?")
        return (
            f"File upload gần nhất: {name}."
            if vi
            else f"Most recent upload: {name}."
        )
    if op == "notebook_info":
        nb = result.get("notebook")
        if not nb:
            return ("Không tìm thấy notebook." if vi else "Notebook not found.")
        return (
            f"Notebook: {nb.get('title', '?')} ({nb.get('document_count', 0)} docs)."
            if vi
            else
            f"Notebook: {nb.get('title', '?')} ({nb.get('document_count', 0)} docs)."
        )
    if op == "find_document":
        matches = result.get("matches") or []
        if not matches:
            return (
                f"Không tìm thấy tài liệu khớp với {result.get('name_like')!r}."
                if vi
                else f"No documents match {result.get('name_like')!r}."
            )
        names = ", ".join(d.get("filename", "?") for d in matches[:5])
        return (
            f"Tìm thấy: {names}." if vi else f"Found: {names}."
        )
    if op == "document_page":
        chunks = result.get("chunks") or []
        page = result.get("page")
        if not chunks:
            return (
                f"Không có nội dung trang {page}." if vi
                else f"No content found on page {page}."
            )
        # Show first chunk text.
        first = chunks[0].get("text", "")
        return first[:600] + ("..." if len(first) > 600 else "")
    return ("Không có dữ liệu." if vi else "No data.")


def _metadata_error_text(language: str | None, detail: str) -> str:
    vi = (language or "").lower() == "vi"
    if vi:
        return (
            "Em không truy vấn được metadata lúc này. "
            "Bạn thử lại sau nhé."
        )
    return "I couldn't look up that metadata right now. Please try again."


def _build_numbered_context(matches: list[dict[str, Any]]) -> str:
    """`[i] {snippet}` block from matches."""
    lines: list[str] = []
    for i, match in enumerate(matches, start=1):
        text = str(match.get("text") or "").strip()
        if len(text) > _CONTEXT_SNIPPET_CHAR_CAP:
            text = text[:_CONTEXT_SNIPPET_CHAR_CAP].rstrip() + "..."
        lines.append(f"[{i}] {text}")
    return "\n".join(lines)


def _match_to_citation(match: dict[str, Any]) -> dict[str, Any]:
    """Normalise vector-search hit into Citation schema shape."""
    snippet = str(match.get("text") or "").strip()
    if len(snippet) > _CITATION_SNIPPET_CHAR_CAP:
        snippet = snippet[:_CITATION_SNIPPET_CHAR_CAP].rstrip() + "..."
    raw_score = match.get("score", 0.0)
    try:
        score = max(0.0, min(1.0, float(raw_score)))
    except (TypeError, ValueError):
        score = 0.0
    # Page lives inside metadata (VectorMatch.metadata carries chunker payload).
    page: int | None = None
    raw_page = (match.get("metadata") or {}).get("page")
    if raw_page is not None:
        try:
            page = int(raw_page)
        except (TypeError, ValueError):
            page = None
    return {
        "document_id": match["document_id"],
        "chunk_id": str(match.get("chunk_id") or ""),
        "snippet": snippet,
        "score": score,
        "page": page,
    }
