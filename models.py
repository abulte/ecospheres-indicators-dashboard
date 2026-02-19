from datetime import datetime
from typing import Any, Optional

import sqlalchemy as sa
from sqlmodel import Field, Relationship, SQLModel


class CrawlState(SQLModel, table=True):
    __tablename__ = "crawlstate"

    id: Optional[int] = Field(default=None, primary_key=True)
    environment: str = Field(unique=True, index=True)
    status: str = Field(default="idle")  # idle | running | completed | failed
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    indicator_count: Optional[int] = None
    error: Optional[str] = None


class Indicator(SQLModel, table=True):
    __tablename__ = "indicator"

    id: Optional[int] = Field(default=None, primary_key=True)
    environment: str = Field(index=True)
    dataset_id: str = Field(index=True)
    title: str
    slug: str
    enable_visualization: bool = False
    has_ecospheres_extras: bool = False
    # checks: [{"name": str, "ok": bool, "detail": any}]
    checks: Optional[list[dict[str, Any]]] = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )
    resource_count: int = 0

    resources: list["Resource"] = Relationship(
        back_populates="indicator",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class Resource(SQLModel, table=True):
    __tablename__ = "resource"

    id: Optional[int] = Field(default=None, primary_key=True)
    indicator_id: int = Field(foreign_key="indicator.id")
    resource_id: str
    title: str
    url: Optional[str] = None
    format: Optional[str] = None
    filetype: Optional[str] = None
    resource_type: Optional[str] = None
    tabular_api_url: Optional[str] = None
    # checks: [{"name": str, "ok": bool, "detail": any}]
    checks: Optional[list[dict[str, Any]]] = Field(
        default=None, sa_column=sa.Column(sa.JSON, nullable=True)
    )
    # convenience bool: all tabular checks passed
    tabular_api_ok: bool = False

    indicator: Optional[Indicator] = Relationship(back_populates="resources")
