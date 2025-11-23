from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, Numeric, SmallInteger, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from apps.bot.db import Base

JSONType = JSON().with_variant(JSONB, "postgresql")
PKBigInt = BigInteger().with_variant(Integer, "sqlite")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    locale: Mapped[str | None] = mapped_column(String(8))
    banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)
    first_deposit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_code: Mapped[str | None] = mapped_column(String(16), unique=True)
    paid_spins_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    paid_crash_bets_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    wallet: Mapped["Wallet"] = relationship(back_populates="user", uselist=False)


class Wallet(Base):
    __tablename__ = "wallets"

    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    coins_cash: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    coins_bonus: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    free_spins_left: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="wallet")


class BonusAwardStatus(str, Enum):
    ACTIVE = "active"
    READY = "ready"
    COMPLETED = "completed"
    EXPIRED = "expired"


class BonusAward(Base):
    __tablename__ = "bonus_awards"

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    granted: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wr_mult: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False)
    turnover_required: Mapped[int] = mapped_column(BigInteger, nullable=False)
    turnover_progress: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    cap_cashout: Mapped[int] = mapped_column(BigInteger, nullable=False)
    cashed_out: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=BonusAwardStatus.ACTIVE.value, server_default=BonusAwardStatus.ACTIVE.value)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)
    unlocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()


class TurnoverRule(Base):
    __tablename__ = "turnover_rules"
    __table_args__ = (UniqueConstraint("game", name="uq_turnover_rules_game"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game: Mapped[str] = mapped_column(String(32), nullable=False)
    contribution: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=100, server_default="100")


class Purchase(Base):
    __tablename__ = "purchases"
    __table_args__ = (UniqueConstraint("charge_id", name="uq_purchases_charge"),)

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="SET NULL"))
    charge_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_code: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_xtr: Mapped[int] = mapped_column(Integer, nullable=False)
    coins_granted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    bonus_granted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed", server_default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), onupdate=func.now(), nullable=False)


class Refund(Base):
    __tablename__ = "refunds"

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    purchase_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("purchases.id", ondelete="CASCADE"), nullable=False)
    amount_xtr: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)


class Ledger(Base):
    __tablename__ = "ledger"
    __table_args__ = (
        CheckConstraint("currency IN ('coins_cash','coins_bonus')", name="ck_ledger_currency"),
    )

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    award_id: Mapped[int | None] = mapped_column(PKBigInt, ForeignKey("bonus_awards.id", ondelete="SET NULL"))
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    __table_args__ = (UniqueConstraint("user_id", "flag", name="uq_feature_flags_user_flag"),)

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"))
    flag: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[str] = mapped_column(String(32), nullable=False, default="on", server_default="on")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), server_default=func.now(), nullable=False)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    props: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="bot", server_default="bot")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Spin(Base):
    __tablename__ = "spins"

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    bet_coins_cash: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    bet_coins_bonus: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    dice_value: Mapped[int] = mapped_column(Integer, nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSONType, nullable=False)
    multiplier: Mapped[float] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    payout_cash: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    payout_bonus: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DuelState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class Duel(Base):
    __tablename__ = "duels"
    __table_args__ = (
        Index("ix_duels_pair_key", "pair_key"),
        Index("ix_duels_chat", "chat_id"),
    )

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    message_id: Mapped[int | None] = mapped_column(BigInteger)
    thread_id: Mapped[int | None] = mapped_column(BigInteger)
    starter_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    opponent_id: Mapped[int | None] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"))
    winner_id: Mapped[int | None] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="SET NULL"))
    stake_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stake_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    bank_cash: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    bank_bonus: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    wins_starter: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    wins_opponent: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    rounds: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default=DuelState.PENDING.value, server_default=DuelState.PENDING.value)
    pair_key: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GiftStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    FULFILLED = "fulfilled"


class Gift(Base):
    __tablename__ = "gifts"

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    bonus_cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    xtr_cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=GiftStatus.PENDING.value, server_default=GiftStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict | None] = mapped_column(JSONType, nullable=True)


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (UniqueConstraint("invitee_id", name="uq_referrals_invitee"),)

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    ref_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    inviter_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invitee_id: Mapped[int | None] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"))
    activated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TreasuryState(Base):
    __tablename__ = "treasury_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    current_xtr: Mapped[int] = mapped_column(BigInteger, nullable=False)
    gift_liability: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    budget_spent_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    budget_spent_xtr: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class CrashRoundStatus(str, Enum):
    BETTING = "betting"
    FLYING = "flying"
    CRASHED = "crashed"


class CrashBetStatus(str, Enum):
    ACTIVE = "active"
    CASHED_OUT = "cashed_out"
    CRASHED = "crashed"


class CrashRound(Base):
    __tablename__ = "crash_rounds"
    __table_args__ = (
        Index("ix_crash_rounds_status", "status"),
        Index(
            "uq_crash_rounds_active",
            "status",
            unique=True,
            sqlite_where=text("status IN ('betting','flying')"),
            postgresql_where=text("status IN ('betting','flying')"),
        ),
    )

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CrashRoundStatus.BETTING.value, server_default=CrashRoundStatus.BETTING.value)
    seed: Mapped[str] = mapped_column(String(128), nullable=False)
    seed_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    crash_point: Mapped[float | None] = mapped_column(Numeric(10, 4))
    bet_ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    crash_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    bets: Mapped[list["CrashBet"]] = relationship(back_populates="round")


class CrashBet(Base):
    __tablename__ = "crash_bets"
    __table_args__ = (
        Index("ix_crash_bets_round_user", "round_id", "user_id"),
        UniqueConstraint("round_id", "user_id", name="uq_crash_bets_round_user"),
    )

    id: Mapped[int] = mapped_column(PKBigInt, primary_key=True, autoincrement=True)
    round_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("crash_rounds.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(PKBigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount_cash: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    amount_bonus: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    auto_cashout: Mapped[float | None] = mapped_column(Numeric(10, 4))
    cashout_multiplier: Mapped[float | None] = mapped_column(Numeric(10, 4))
    payout_cash: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CrashBetStatus.ACTIVE.value, server_default=CrashBetStatus.ACTIVE.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    cashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    round: Mapped[CrashRound] = relationship(back_populates="bets")
    user: Mapped[User] = relationship()
