import enum
from datetime import datetime
from sqlalchemy import BigInteger, String, Enum as SQLEnum, ForeignKey, func, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

class ChannelStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    PERMISSION_ERROR = "permission_error"
    REMOVED = "removed"

class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    owner_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[ChannelStatus] = mapped_column(
        SQLEnum(ChannelStatus, name="channel_status"),
        default=ChannelStatus.ACTIVE,
        nullable=False
    )
    custom_footer: Mapped[str] = mapped_column(String, nullable=True)
    auto_pin_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    queue_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    queue_interval_minutes: Mapped[int] = mapped_column(Integer, default=15, server_default="15", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationship to event logs
    logs: Mapped[list["EventLog"]] = relationship(
        "EventLog",
        back_populates="channel",
        cascade="all, delete-orphan"
    )

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=True)
    first_name: Mapped[str] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False
    )
    message_type: Mapped[str] = mapped_column(String, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Back relation to channel
    channel: Mapped["Channel"] = relationship("Channel", back_populates="logs")

class QueuePost(Base):
    __tablename__ = "queue_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False
    )
    message_data: Mapped[str] = mapped_column(String, nullable=False)  # JSON payload
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    channel: Mapped["Channel"] = relationship("Channel")

