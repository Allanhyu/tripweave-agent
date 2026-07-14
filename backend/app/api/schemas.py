"""Pydantic schemas for the HTTP API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TripPlanRequestBody(BaseModel):
    city: str = Field(..., examples=["Beijing,CN"])
    start_date: str = Field(..., examples=["2026-07-08"])
    days: int = Field(..., ge=1, le=60)
    cities: List[Dict[str, Any]] = Field(default_factory=list, max_length=6)
    travelers: int = Field(default=1, ge=1, le=20)
    max_budget: float = Field(default=0, ge=0)
    preferences: List[str] = Field(default_factory=list)
    pace: str = Field(default="moderate")
    accommodation: str = Field(default="standard hotel")
    transportation: str = Field(default="public transit")
    special_requirements: str = Field(default="")
    include_packing: bool = Field(default=True)


class TripPlanResponseBody(BaseModel):
    success: bool
    content: str
    step_count: int
    raw_steps: List[Dict[str, Any]]
    warning: Optional[str] = None
    structured_plan: Optional[Dict[str, Any]] = None
    knowledge_graph: Optional[Dict[str, Any]] = None


class ErrorResponseBody(BaseModel):
    success: bool = False
    detail: str


class UserMemoryBody(BaseModel):
    default_city: str = Field(default="北京")
    travelers: int = Field(default=2, ge=1, le=20)
    max_budget: float = Field(default=3000, ge=0)
    preferences: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    pace: str = Field(default="moderate")
    accommodation: str = Field(default="standard hotel")
    transportation: str = Field(default="public transit")
    include_packing: bool = Field(default=True)
