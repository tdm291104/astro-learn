"""Single source of truth for `agent_name -> configured BaseAgent`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agents.base.agent_registry import AgentRegistry
from agents.base.base_agent import BaseAgent
from core.config import Settings
from core.llm.llm_client import LLMClient
from memory.long_term.catalog_cache import CatalogCache
from memory.long_term.vector_store import VectorStore
from memory.short_term.conversation_memory import ConversationMemory
from services._agent_run_recorder import AgentRunRecorder
from tools.astronomy.astropy_tool import AstropyTool
from tools.astronomy.fits_reader_tool import FitsReaderTool
from tools.astronomy.nasa_api_tool import NasaApiTool
from tools.astronomy.ned_tool import NedTool
from tools.astronomy.simbad_tool import SimbadTool
from tools.astronomy.symbolic_checker_tool import SymbolicFitsCheckerTool
from tools.astronomy.vizier_tool import VizierTool
from tools.base_tool import BaseTool
from tools.knowledge.notebook_metadata_tool import NotebookMetadataTool
from tools.knowledge.pdf_parser_tool import PdfParserTool
from tools.knowledge.vector_search_tool import VectorSearchTool
from tools.knowledge.web_search_tool import WebSearchTool


class DefaultAgentFactory:
    """Builds an agent and its tool list from the registry name."""

    def __init__(
        self,
        *,
        llm: LLMClient,
        settings: Settings,
        vector_store: VectorStore,
        redis: Redis,
        http_client: httpx.AsyncClient,
        storage_root: Path,
        catalog_cache: CatalogCache | None = None,
        conversation_memory: ConversationMemory | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        recorder: AgentRunRecorder | None = None,
    ) -> None:
        self.llm = llm
        self.settings = settings
        self.vector_store = vector_store
        self.redis = redis
        self.http_client = http_client
        self.storage_root = storage_root
        # Optional for test factories without DB session.
        self.catalog_cache = catalog_cache
        # Only OrchestratorAgent receives it.
        self.conversation_memory = conversation_memory
        # Enables cooperative cancellation polling in long-running agents.
        self.session_factory = session_factory
        # Consumed only by FitsAnalystAgent's services bundle.
        self.recorder = recorder

    def __call__(self, agent_name: str) -> BaseAgent:
        """Return a fresh agent instance ready to run."""
        agent_cls = AgentRegistry.get(agent_name)
        tools = self._tools_for(agent_name)
        extra = self._extra_kwargs(agent_name)
        return agent_cls(llm=self.llm, tools=tools, **extra)

    def _extra_kwargs(self, agent_name: str) -> dict[str, Any]:
        """Return per-agent constructor extras beyond llm and tools."""
        if agent_name == "orchestrator":
            # None settings → treat as production default (True).
            memory_enabled = (
                self.settings.ENABLE_CHAT_HISTORY_MEMORY
                if self.settings is not None
                else True
            )
            return {
                "factory": self,
                "conversation_memory": self.conversation_memory,
                "memory_enabled": memory_enabled,
                "session_factory": self.session_factory,
            }
        if agent_name == "image_processor":
            return {"storage_root": self.storage_root}
        if agent_name == "catalog" and self.catalog_cache is not None:
            return {"catalog_cache": self.catalog_cache}
        # session_factory enables cancellation polling between steps.
        if agent_name == "data_analyst" and self.session_factory is not None:
            return {"session_factory": self.session_factory}
        if (
            agent_name == "fits_analyst"
            and self.session_factory is not None
            and self.recorder is not None
        ):
            # Local import to break cycle with AstronomyService.
            from agents.astronomy.fits_analyst_services import DefaultFitsAnalystServices

            services = DefaultFitsAnalystServices(
                session_factory=self.session_factory,
                storage_root=self.storage_root,
                recorder=self.recorder,
                agent_factory=self,
            )
            return {
                "services": services,
                "symbolic_checker": self._symbolic_checker(),
            }
        # Extraction-shaped tasks use the cheaper/faster model.
        if (
            agent_name in {"quiz", "flashcard", "summarizer"}
            and self.settings is not None
        ):
            return {"model": self.settings.LLM_FAST_MODEL}
        return {}

    def _tools_for(self, agent_name: str) -> list[BaseTool]:
        """Return the tool list expected by the agent named agent_name."""
        if agent_name == "retriever":
            return [self._vector_search()]
        # NasaApiTool lives on orchestrator (NASA Open APIs, not NED).
        if agent_name == "catalog":
            return [self._simbad(), self._ned(), self._vizier()]
        if agent_name == "catalog_chat":
            return [self._web_search()]
        if agent_name == "data_analyst":
            return [self._fits_reader(), self._astropy()]
        if agent_name == "reflexion_data_analyst":
            return [self._fits_reader(), self._astropy(), self._symbolic_checker()]
        if agent_name == "fits_analyst":
            # Agent drives RunFitsAnalysisTool internally via services bundle.
            return []
        if agent_name == "image_processor":
            return [self._fits_reader(), self._astropy()]
        if agent_name == "orchestrator":
            base: list[BaseTool] = [self._nasa_api(), self._web_search()]
            metadata = self._notebook_metadata()
            if metadata is not None:
                base.append(metadata)
            return base
        if agent_name == "qa":
            tools: list[BaseTool] = [self._vector_search()]
            metadata = self._notebook_metadata()
            if metadata is not None:
                tools.append(metadata)
            return tools
        if agent_name in {"summarizer", "quiz", "flashcard"}:
            return [self._vector_search()]
        return []

    def _vector_search(self) -> VectorSearchTool:
        return VectorSearchTool(store=self.vector_store)

    def _notebook_metadata(self) -> NotebookMetadataTool | None:
        """Built only when a session_factory is available (skipped in tests)."""
        if self.session_factory is None:
            return None
        return NotebookMetadataTool(
            session_factory=self.session_factory,
            vector_store=self.vector_store,
        )

    def _pdf_parser(self) -> PdfParserTool:
        # Not wired into agents; worker uses directly. Kept for symmetry/tests.
        return PdfParserTool(storage_root=self.storage_root)

    def _fits_reader(self) -> FitsReaderTool:
        return FitsReaderTool(storage_root=self.storage_root)

    def _astropy(self) -> AstropyTool:
        return AstropyTool()

    def _symbolic_checker(self) -> SymbolicFitsCheckerTool:
        return SymbolicFitsCheckerTool(storage_root=self.storage_root)

    def _simbad(self) -> SimbadTool:
        return SimbadTool()

    def _ned(self) -> NedTool:
        return NedTool()

    def _vizier(self) -> VizierTool:
        return VizierTool()

    def _nasa_api(self) -> NasaApiTool:
        return NasaApiTool(settings=self.settings, http_client=self.http_client)

    def _web_search(self) -> WebSearchTool:
        return WebSearchTool(settings=self.settings, http_client=self.http_client)
