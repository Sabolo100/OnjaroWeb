"""Pydantic models for the research pipeline framework."""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# ── Research Item Definition (loaded from project config) ──

class ResearchItem(BaseModel):
    """Definition of a single research target."""
    id: str
    name: str
    enabled: bool = True
    priority: int = 5
    target_table: str
    search_type: str = "topic_search"
    schema_name: str
    schedule: str = "daily"
    max_results_per_run: int = 5
    topics: List[str] = []
    language: str = "hu"
    content_types: List[str] = []
    min_confidence: float = 0.6
    auto_approve_above: float = 0.8
    manual_review_below: float = 0.4


# ── Source Definition ──

class SourceDefinition(BaseModel):
    """A web source for research."""
    url: str
    trust_score: float = 0.5
    language: str = "hu"
    source_type: str = "web"
    tags: List[str] = []


# ── Pipeline Data Models ──

class RawFinding(BaseModel):
    """Raw data fetched from the web."""
    finding_id: Optional[int] = None
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    source_domain: Optional[str] = None
    search_query: Optional[str] = None
    connector_used: Optional[str] = None
    fetched_at: Optional[datetime] = None


class ExtractionCandidate(BaseModel):
    """Structured data extracted from a raw finding."""
    candidate_id: Optional[int] = None
    finding_id: int
    item_id: str
    extracted_data: Dict[str, Any]
    confidence: float = 0.0
    status: str = "pending"
    rejection_reason: Optional[str] = None


class NormalizedRecord(BaseModel):
    """A validated, normalized record ready for persistence."""
    candidate_id: int
    data: Dict[str, Any]
    confidence: float
    target_table: str


class DedupeResult(BaseModel):
    """Result of deduplication check."""
    candidate_id: int
    action: Literal["new", "duplicate", "update_candidate", "ambiguous"]
    existing_id: Optional[str] = None
    similarity_score: Optional[float] = None
    reason: Optional[str] = None
    record: Dict[str, Any] = {}


class PersistenceResult(BaseModel):
    """What happened when trying to persist a record."""
    candidate_id: int
    action: Literal["inserted", "updated", "skipped", "rejected", "needs_review"]
    target_id: Optional[str] = None
    target_table: Optional[str] = None
    reason: Optional[str] = None


# ── Policy Models ──

class DedupePolicy(BaseModel):
    """Deduplication configuration."""
    strategy: str = "title_similarity"
    similarity_threshold: float = 0.85
    unique_keys: List[str] = ["title", "type"]


class PersistencePolicy(BaseModel):
    """How to handle persistence decisions."""
    default_policy: str = "insert_if_new"
    review_threshold: float = 0.6


class ApprovalPolicy(BaseModel):
    """Autonomy thresholds for auto-approval."""
    auto_approve_above: float = 0.8
    require_manual_below: float = 0.4


class ProjectPolicies(BaseModel):
    """All policies for a project."""
    dedupe: DedupePolicy = DedupePolicy()
    persistence: PersistencePolicy = PersistencePolicy()
    approval: ApprovalPolicy = ApprovalPolicy()


# ── Run Summary ──

class ResearchRunSummary(BaseModel):
    """Summary of a completed research run."""
    run_id: str
    items_total: int = 0
    items_completed: int = 0
    items_failed: int = 0
    raw_findings_total: int = 0
    extracted_total: int = 0
    persisted_total: int = 0
    skipped_total: int = 0
    review_queue_total: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
