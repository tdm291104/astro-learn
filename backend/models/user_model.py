"""User account ORM model."""

from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base_model import Base, IdMixin, TimestampMixin

if TYPE_CHECKING:
    from models.agent_model import AgentModel
    from models.notebook_model import NotebookModel
    from models.session_model import SessionModel


class UserModel(Base, IdMixin, TimestampMixin):
    """A registered user account."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Gates /admin/* routes; promoted via promote_admin script only.
    is_admin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa.false()
    )

    notebooks: Mapped[list[NotebookModel]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[list[SessionModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    agent_runs: Mapped[list[AgentModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
