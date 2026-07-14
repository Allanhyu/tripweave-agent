"""Domain data structures for trip planning."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TripPlanningRequest:
    city: str
    start_date: str
    days: int
    cities: List[dict] = field(default_factory=list)
    travelers: int = 1
    max_budget: float = 0
    preferences: List[str] = field(default_factory=list)
    pace: str = "moderate"
    accommodation: str = "standard hotel"
    transportation: str = "public transit"
    special_requirements: str = ""
    include_packing: bool = True


@dataclass
class TripPlanningResponse:
    content: str
    step_count: int
    raw_steps: List[dict]
    warning: Optional[str] = None
