"""Importing this package registers every concrete agent."""

# Side-effect imports populate AgentRegistry.
from agents.astronomy import (  # noqa: F401
    catalog_agent,
    catalog_chat_agent,
    data_analyst_agent,
    fits_analyst_agent,
    image_processor_agent,
    reflexion_data_analyst_agent,
)
from agents.notebook import (  # noqa: F401
    flashcard_agent,
    qa_agent,
    quiz_agent,
    summarizer_agent,
)
from agents.orchestrator import orchestrator_agent  # noqa: F401
from agents.support import retriever_agent, validator_agent  # noqa: F401
