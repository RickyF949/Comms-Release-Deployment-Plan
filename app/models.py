import reflex as rx

from datetime import date, datetime, timezone
from secrets import token_urlsafe
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    select,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import Select


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Merchant(Base):
    __tablename__ = "merchant"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(255), default="", server_default=""
    )
    webhook_token: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        default=lambda: token_urlsafe(32),
    )
    sms_sender: Mapped[str] = mapped_column(
        String(64), default="", server_default=""
    )
    business_hours_tz: Mapped[str] = mapped_column(
        String(128),
        default="Australia/Sydney",
        server_default="Australia/Sydney",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    pending_comms: Mapped[list["PendingComm"]] = relationship(
        back_populates="merchant",
        passive_deletes="all",
    )


class PendingComm(Base):
    __tablename__ = "pending_comm"
    __table_args__ = (
        UniqueConstraint(
            "merchant_id", "job_id", name="uq_pending_comm_merchant_job"
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'sent', 'failed')",
            name="valid_status",
        ),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempt_count"),
        CheckConstraint("claim_version >= 0", name="nonnegative_claim_version"),
        CheckConstraint(
            "(status = 'processing' AND claim_token IS NOT NULL "
            "AND claimed_at IS NOT NULL AND claim_expires_at IS NOT NULL "
            "AND claimed_by IS NOT NULL AND attempt_count > 0 "
            "AND claim_expires_at > claimed_at) OR "
            "(status <> 'processing' AND claim_token IS NULL "
            "AND claimed_at IS NULL AND claim_expires_at IS NULL AND claimed_by IS NULL)",
            name="consistent_claim",
        ),
        Index(
            "ix_pending_comm_status_delivery_received",
            "status",
            "delivery_day",
            "received_at",
            "id",
        ),
        Index("ix_pending_comm_merchant_status", "merchant_id", "status"),
        Index(
            "ix_pending_comm_status_claim_expiry", "status", "claim_expires_at"
        ),
        Index(
            "ix_pending_comm_status_next_attempt", "status", "next_attempt_at"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    job_id: Mapped[str] = mapped_column(
        String(255),
        default=lambda: uuid4().hex,
    )
    merchant_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("merchant.id", ondelete="RESTRICT"),
        nullable=False,
    )
    customer_name: Mapped[str] = mapped_column(
        String(255), default="", server_default=""
    )
    customer_phone: Mapped[str] = mapped_column(
        String(32), default="", server_default=""
    )
    delivery_day: Mapped[date] = mapped_column(
        Date,
        default=date.today,
        server_default=text("CURRENT_DATE"),
    )
    status: Mapped[str] = mapped_column(
        String(16),
        default="pending",
        server_default="pending",
        index=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    claim_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    claim_token: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), default=None, unique=True
    )
    claimed_by: Mapped[str | None] = mapped_column(String(255), default=None)
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    merchant: Mapped[Merchant] = relationship(back_populates="pending_comms")
    communication_logs: Mapped[list["CommunicationLog"]] = relationship(
        back_populates="pending_job",
        passive_deletes="all",
        order_by="CommunicationLog.attempt_number",
    )


class CommunicationLog(Base):
    __tablename__ = "communication_log"
    __table_args__ = (
        UniqueConstraint(
            "pending_job_id",
            "attempt_number",
            name="uq_communication_log_job_attempt",
        ),
        CheckConstraint("attempt_number > 0", name="positive_attempt_number"),
        CheckConstraint("claim_version >= 0", name="nonnegative_claim_version"),
        CheckConstraint(
            "http_status IS NULL OR (http_status >= 100 AND http_status <= 599)",
            name="valid_http_status",
        ),
        Index(
            "ix_communication_log_job_timestamp",
            "pending_job_id",
            "timestamp",
            "id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pending_job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("pending_comm.id", ondelete="RESTRICT"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1"
    )
    claim_token: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), default=uuid4, unique=True
    )
    claim_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    http_status: Mapped[int | None] = mapped_column(Integer, default=None)
    http_response: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    pending_job: Mapped[PendingComm] = relationship(
        back_populates="communication_logs"
    )


def ordered_pending_jobs_statement() -> Select[tuple[PendingComm]]:
    """Build a deterministic queue SELECT without opening a session or executing it."""
    return (
        select(PendingComm)
        .where(PendingComm.status == "pending")
        .order_by(
            PendingComm.received_at.asc(),
            PendingComm.id.asc(),
        )
    )
