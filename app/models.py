import secrets
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.timeutil import now_local


def _new_qr_token() -> str:
    return secrets.token_urlsafe(6)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    # Deterministic HMAC of the normalized phone number. Used to recognise a
    # returning predictor so season stats follow the person, not whatever
    # name/nickname they happened to type in.
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Fernet-encrypted normalized phone number. Recoverable only via the
    # PHONE_ENCRYPTION_KEY secret (e.g. scripts/decrypt_phone.py); never
    # decrypted or shown anywhere in the web UI.
    phone_encrypted: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    predictions: Mapped[list["Prediction"]] = relationship(back_populates="player")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opponent: Mapped[str] = mapped_column(String(120))
    competition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(120), nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime)
    buy_in_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    bok_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opponent_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_entered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    qr_token: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, default=_new_qr_token
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)

    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="match", cascade="all, delete-orphan"
    )

    @property
    def is_resolved(self) -> bool:
        return self.bok_score is not None and self.opponent_score is not None

    @property
    def is_locked(self) -> bool:
        """Predictions can no longer be made or edited."""
        return self.is_resolved or now_local() >= self.kickoff_at

    @property
    def has_winner(self) -> bool:
        return self.is_resolved and any(p.is_winner for p in self.predictions)

    @property
    def paid_contribution(self) -> float:
        paid_count = sum(1 for p in self.predictions if p.paid)
        return float(self.buy_in_amount) * paid_count


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("match_id", "player_id", name="uq_match_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))

    predicted_bok_score: Mapped[int] = mapped_column(Integer)
    predicted_opponent_score: Mapped[int] = mapped_column(Integer)

    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False)

    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=now_local)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_local, onupdate=now_local
    )

    match: Mapped["Match"] = relationship(back_populates="predictions")
    player: Mapped["Player"] = relationship(back_populates="predictions")

    @property
    def diff(self) -> int:
        """Absolute point difference from the actual result. Lower is closer."""
        if not self.match.is_resolved:
            return -1
        return abs(self.predicted_bok_score - self.match.bok_score) + abs(
            self.predicted_opponent_score - self.match.opponent_score
        )


class AppSettings(Base):
    """Singleton settings row (id is always 1)."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    # Carry-over pot balance from before the app was used, or a manual admin
    # correction. Added on top of the computed contributions since last win.
    starting_pot_balance: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
