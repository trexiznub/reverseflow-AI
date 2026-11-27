"""SQLAlchemy ORM models.

Portable column types only, so the schema maps 1:1 to PostgreSQL / SAP HANA Cloud.
Every record created by the generator carries is_synthetic=True.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(60))
    onboarded: Mapped[date] = mapped_column(Date)
    specialty: Mapped[str] = mapped_column(String(60))
    qc_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Product(Base):
    __tablename__ = "products"
    sku: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    price: Mapped[float] = mapped_column(Float)
    fabric: Mapped[str] = mapped_column(String(40))
    colour: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text)
    size_chart: Mapped[dict] = mapped_column(JSON)  # {"S": {"bust": 34, ...}}
    size_chart_version: Mapped[int] = mapped_column(Integer, default=1)
    season: Mapped[str] = mapped_column(String(40))  # festive / wedding / all-season
    pre_dispatch_qc: Mapped[bool] = mapped_column(Boolean, default=False)
    exchange_first: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class PinCluster(Base):
    __tablename__ = "pin_clusters"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    city: Mapped[str] = mapped_column(String(60))
    state: Mapped[str] = mapped_column(String(60))
    pin_prefix: Mapped[str] = mapped_column(String(8))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    # Network-scale baseline: average daily ethnicwear returns across the whole
    # marketplace in this cluster during normal weeks (illustrative assumption).
    network_daily_returns: Mapped[int] = mapped_column(Integer)
    default_facility_id: Mapped[str] = mapped_column(String(16))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(60))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(30))  # hub / returns-centre
    inspection_capacity: Mapped[int] = mapped_column(Integer)  # units/day, network scale
    storage_capacity: Mapped[int] = mapped_column(Integer)
    normal_load: Mapped[int] = mapped_column(Integer)  # units/day in normal weeks
    handling_cost: Mapped[float] = mapped_column(Float)  # INR per unit inspected
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class LogisticsProvider(Base):
    __tablename__ = "logistics_providers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    clusters: Mapped[list] = mapped_column(JSON)
    vehicles: Mapped[int] = mapped_column(Integer)
    pickups_per_vehicle: Mapped[int] = mapped_column(Integer)  # per day
    cost_per_pickup: Mapped[float] = mapped_column(Float)
    sla_hours: Mapped[int] = mapped_column(Integer, default=48)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    cluster_id: Mapped[str] = mapped_column(ForeignKey("pin_clusters.id"), index=True)
    pin: Mapped[str] = mapped_column(String(8))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), index=True)
    size: Mapped[str] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Float)
    order_date: Mapped[date] = mapped_column(Date, index=True)
    delivered_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("pin_clusters.id"), index=True)
    festival_tag: Mapped[str | None] = mapped_column(String(30), nullable=True)
    serial_no: Mapped[str] = mapped_column(String(24))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Return(Base):
    __tablename__ = "returns"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), index=True)
    vendor_id: Mapped[str] = mapped_column(ForeignKey("vendors.id"), index=True)
    cluster_id: Mapped[str] = mapped_column(ForeignKey("pin_clusters.id"), index=True)
    size: Mapped[str] = mapped_column(String(8))
    price: Mapped[float] = mapped_column(Float)
    request_date: Mapped[date] = mapped_column(Date, index=True)
    reason_category: Mapped[str] = mapped_column(String(30))  # what customer picked (coarse)
    reason_text: Mapped[str] = mapped_column(Text)
    verified_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)  # inspection-verified label
    predicted_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)  # NLP output
    reason_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolution: Mapped[str] = mapped_column(String(20), default="refund")  # refund / exchange
    exchange_size: Mapped[str | None] = mapped_column(String(8), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    pickup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    pickup_slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    inspected_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    facility_id: Mapped[str | None] = mapped_column(ForeignKey("facilities.id"), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(ForeignKey("logistics_providers.id"), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(2), nullable=True)
    defects: Mapped[str | None] = mapped_column(String(120), nullable=True)
    recovery_action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    recovered_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    refund_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    refund_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    restock_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # integrity evidence captured at pickup / receiving
    tag_intact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    serial_returned: Mapped[str | None] = mapped_column(String(24), nullable=True)
    weight_delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    images_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    integrity_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    pickup_sla_met: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pickup_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_via: Mapped[str] = mapped_column(String(20), default="generator")  # generator / portal
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class ReturnEvent(Base):
    __tablename__ = "return_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_id: Mapped[str] = mapped_column(ForeignKey("returns.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    customer_visible: Mapped[bool] = mapped_column(Boolean, default=True)


class ReturnImage(Base):
    __tablename__ = "return_images"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_id: Mapped[str] = mapped_column(ForeignKey("returns.id"), index=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    path: Mapped[str] = mapped_column(String(300))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime)


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(ForeignKey("products.sku"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    order_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rating: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    review_date: Mapped[date] = mapped_column(Date)
    sentiment: Mapped[float | None] = mapped_column(Float, nullable=True)
    topic: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class FacilityDaily(Base):
    __tablename__ = "facility_daily"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    facility_id: Mapped[str] = mapped_column(ForeignKey("facilities.id"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    inbound: Mapped[int] = mapped_column(Integer)
    processed: Mapped[int] = mapped_column(Integer)
    backlog: Mapped[int] = mapped_column(Integer)
    utilisation: Mapped[float] = mapped_column(Float)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)


class Festival(Base):
    __tablename__ = "festivals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(60))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(20))  # festival / wedding-season


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(120))
    scope_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    approval_limit: Mapped[float] = mapped_column(Float, default=0)


class Recommendation(Base):
    """Agent recommendations. Consequential ones go through the approval workflow."""
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    agent: Mapped[str] = mapped_column(String(40), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    rationale: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(40))
    impact_inr: Mapped[float] = mapped_column(Float, default=0)
    cost_inr: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    approver_role: Mapped[str] = mapped_column(String(30), default="ops_manager")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation_source: Mapped[str] = mapped_column(String(40), default="template")
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class DecisionLog(Base):
    __tablename__ = "decision_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(24))
    user_name: Mapped[str] = mapped_column(String(80))
    role: Mapped[str] = mapped_column(String(30))
    ts: Mapped[datetime] = mapped_column(DateTime)
    action: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    previous_status: Mapped[str] = mapped_column(String(20))
    new_status: Mapped[str] = mapped_column(String(20))


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    actor_type: Mapped[str] = mapped_column(String(20))  # user / agent / system
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(30))
    entity_id: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON)


class OrchestratorRun(Base):
    __tablename__ = "orchestrator_runs"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    trigger: Mapped[str] = mapped_column(String(40))
    event: Mapped[dict] = mapped_column(JSON)
    plan: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    conflicts: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("orchestrator_runs.id"), index=True)
    agent: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20))  # queued/running/completed/failed/skipped
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    outputs: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("orchestrator_runs.id"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime)
    sender: Mapped[str] = mapped_column(String(40))
    receiver: Mapped[str] = mapped_column(String(40))
    topic: Mapped[str] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSON)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    agent: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    audience: Mapped[str] = mapped_column(String(30))  # ops_manager / vendor / logistics / warehouse
    scope_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[str] = mapped_column(String(40))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    origin: Mapped[date] = mapped_column(Date)
    payload: Mapped[dict] = mapped_column(JSON)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)


class SapMessage(Base):
    """Outbox of messages for SAP systems (IBP, TM, Ariba), one per business event.

    A message is prepared whenever an approved decision or a forecast affects a
    system that SAP owns. It is delivered when that system is connected;
    otherwise it waits here with status "waiting" and nothing is sent.
    """
    __tablename__ = "sap_outbox"
    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    system: Mapped[str] = mapped_column("sap_system", String(10), index=True)  # ibp / tm / ariba
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(20))  # recommendation / forecast
    source_id: Mapped[str] = mapped_column(String(40), index=True)
    created_by: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12), default="waiting", index=True)  # waiting / sent / failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target: Mapped[str | None] = mapped_column(String(300), nullable=True)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
