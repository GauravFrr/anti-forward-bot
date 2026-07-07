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
