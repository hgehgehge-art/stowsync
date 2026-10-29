"""Pure domain contracts. Policy observations deliberately have no future events."""
from dataclasses import dataclass, field, asdict
from hashlib import sha256
import json
from pydantic import BaseModel, Field, model_validator

VERSION = "stowsync-2.0.0"
ASSUMPTIONS = "synthetic-2026-10-v1"
START_ISO = "2026-10-09T09:00:00+09:00"
POLICIES = {"A": "예약 기반", "B": "ETA 기반", "C": "ETA + 사전 재배치"}
PRESETS = {
    "story": "대표 컨테이너 흐름 · 20개",
    "balanced": "균형 운영 · 기본 시나리오",
    "late_priority": "지연 도착 × 선적 상위",
    "late_low": "지연 도착 × 선적 하위",
    "early_priority": "조기 도착 × 선적 상위",
    "early_low": "조기 도착 × 선적 하위",
    "normal": "정상 도착",
    "uncertain": "ETA 오차 확대",
    "capacity": "빈 공간 부족",
    "reversal": "선적 계획 역전",
    "surprise": "사전 이동 중 조기 도착",
    "cutoff": "게이트 마감 초과",
    "premarshal_demo": "유휴시간 선작업 검토",
}

class Config(BaseModel):
    seed: int = Field(7, ge=0, le=999999)
    preset: str = "balanced"
    target_count: int = Field(80, ge=12, le=120)
    occupancy: float = Field(.42, ge=0, le=1)
    eta_error: int = Field(600, ge=30, le=3600)
    concentration: float = Field(.35, ge=0, le=1)
    plan_changes: bool = True
    handling: int = Field(90, ge=15, le=300)
    stack_weight_limit: float = Field(110, ge=35, le=200)
    gate_service: int = Field(60, ge=1)
    internal_travel: int = Field(180, ge=0)
    exit_travel: int = Field(120, ge=0)
    queue_limit: int = Field(10, ge=1)
    horizon: int = Field(14400, ge=300)
    cleanup: int = Field(7200, ge=0)
    samples: int = Field(8, ge=2, le=16)
    lookahead: int = Field(3600, ge=300)
    premarshal: bool = True
    headroom: bool = True
    eta_stale: int = Field(600, ge=60)
    tolerance: int = Field(600, ge=0)
    min_gain: float = Field(60, ge=0)
    min_eta_trust: int = Field(65, ge=0, le=100)

    @model_validator(mode="after")
    def valid_preset(self):
        if self.preset not in PRESETS:
            raise ValueError("preset: 알 수 없는 시나리오")
        return self

@dataclass(frozen=True)
class Container:
    container_id: str
    vessel_id: str
    block: str
    booking_start: int
    booking_end: int
    weight_t: float
    initial: bool = False
    size_ft: int = 20
    cargo_type: str = "일반"
    hazard_class: str = ""
    connecting_vessel: str = ""

@dataclass(frozen=True)
class Forecast:
    update_id: str
    observed_at: int
    container_id: str
    p10: int
    p50: int
    p90: int
    source: str = "synthetic_forecast"
    trust_score: int = 80

@dataclass(frozen=True)
class PlanEntry:
    container_id: str
    sequence: int
    due: int
    group: int = 1

@dataclass(frozen=True)
class Event:
    at: int
    kind: str
    event_id: str
    payload: dict

@dataclass
class ScenarioBundle:
    config: Config
    containers: dict[str, Container]
    initial_yard: dict[str, list[str]]
    initial_plan: dict[str, PlanEntry]
    forecasts: list[Forecast]
    truth_events: list[Event]
    vessels: dict[str, dict]

@dataclass
class Observation:
    now: int
    containers: dict[str, Container]
    yard: dict[str, list[str]]
    plan: dict[str, PlanEntry]
    forecasts: dict[str, Forecast]
    statuses: dict[str, str]
    crane_busy_until: dict[str, int]
    locked_stacks: set[str]
    headroom: dict[str, dict]
    yard_arrivals: dict[str, int]
    last_premarshal: dict[str, int]
    yard_version: int
    plan_version: str
    config: Config

@dataclass
class Candidate:
    stack: str
    tier: int
    score: float
    extra_seconds: float
    wait_seconds: float
    delay_seconds: float
    blocked_pairs: float
    low: float
    high: float
    sample_scores: list[float]
    reason_codes: list[str]
    move_seconds: int
    rehandles: float = 0
    premarshals: float = 0
    preference: float = 0

@dataclass
class Recommendation:
    recommendation_id: str
    container_id: str
    action: str
    created_at: int
    valid_until: int
    yard_version: int
    plan_version: str
    candidates: list[Candidate]
    status: str = "DRAFT"
    keep_score: float | None = None
    non_worse: int = 0
    reason: str = ""
    keep_rehandles: float = 0

@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    @property
    def valid(self):
        return not self.errors

@dataclass
class RunResult:
    policy: str
    run_id: str
    moves: list[dict]
    trucks: list[dict]
    retrievals: list[dict]
    decisions: list[dict]
    events: list[dict]
    snapshots: list[dict]
    metrics: dict
    manifest: dict

def stable_hash(value) -> str:
    def default(o):
        if isinstance(o, BaseModel): return o.model_dump()
        if isinstance(o, set): return sorted(o)
        return asdict(o)
    return sha256(json.dumps(value, default=default, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]

def stack_keys():
    return [f"{b}-{bay:02d}-{row:02d}" for b in ("A1", "B1") for bay in (1, 2) for row in (1, 2, 3)]

def slot(stack, tier):
    return f"{stack}-{tier:02d}"
