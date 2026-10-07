"""Database models — foundation tables (doc 02 §1 and §10).

Later build steps add their own tables through new Alembic migrations.
"""

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    google_sub: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str | None] = mapped_column(String(200))
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AuthSession(Base):
    """Login sessions. Only a SHA-256 hash of each token is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # pending_2fa | web | extension
    scopes: Mapped[str] = mapped_column(String(200), default="")
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    user_agent: Mapped[str | None] = mapped_column(String(300))


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[object] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    # A loosened risk setting only takes effect after a delay (doc 04 §6).
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Secret(Base):
    """API keys and tokens, Fernet-encrypted. The master key lives in Windows Credential Manager."""

    __tablename__ = "secrets"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    ciphertext: Mapped[str] = mapped_column(Text)
    last4: Mapped[str] = mapped_column(String(4))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(100))
    detail_json: Mapped[dict | None] = mapped_column(JSON)


class DataSourceStatus(Base):
    __tablename__ = "data_source_status"

    source: Mapped[str] = mapped_column(String(50), primary_key=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    freshness_sla_minutes: Mapped[int] = mapped_column(Integer)
    healthy: Mapped[bool] = mapped_column(Boolean, default=False)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_name: Mapped[str] = mapped_column(String(100), index=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(UTCDateTime)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    status: Mapped[str] = mapped_column(String(20))  # running | ok | failed | skipped
    detail: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Rule versions, risk profile, asset split, goals (doc 02 §2 and §7)
# ---------------------------------------------------------------------------


class StrategyVersion(Base):
    """Snapshot of a rules file, so every saved result can say exactly which rules produced it."""

    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    engine: Mapped[str] = mapped_column(String(30))  # profile | mf | stock_lt | swing
    version: Mapped[int] = mapped_column(Integer)
    config_hash: Mapped[str] = mapped_column(String(16), unique=True)
    config_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class RiskProfile(Base):
    __tablename__ = "risk_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    answers_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict] = mapped_column(JSON)
    capacity_score: Mapped[int] = mapped_column(Integer)
    tolerance_category: Mapped[str] = mapped_column(String(20))
    final_category: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    review_due_on: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AllocationTarget(Base):
    """Core / satellite / trading split. A raised trading share only takes effect after `effective_at`."""

    __tablename__ = "allocation_targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("risk_profiles.id"), index=True)
    core_pct: Mapped[int] = mapped_column(Integer)
    satellite_pct: Mapped[int] = mapped_column(Integer)
    trading_pct: Mapped[int] = mapped_column(Integer)
    is_user_override: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(Text)
    warnings_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100))
    goal_type: Mapped[str] = mapped_column(String(30))
    target_amount_today: Mapped[int] = mapped_column(BigInteger)
    inflation_rate: Mapped[float] = mapped_column(Float)
    target_year: Mapped[int] = mapped_column(Integer)
    current_corpus: Mapped[int] = mapped_column(BigInteger, default=0)
    priority: Mapped[int] = mapped_column(Integer, default=2)  # 1 high · 2 medium · 3 low
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


# ---------------------------------------------------------------------------
# Mutual fund reference data and NAV history (doc 02 §3–4)
# ---------------------------------------------------------------------------


class MfScheme(Base):
    __tablename__ = "mf_schemes"

    scheme_code: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)  # AMFI code
    amc: Mapped[str | None] = mapped_column(String(120))
    fund_name: Mapped[str] = mapped_column(String(300))
    display_name: Mapped[str] = mapped_column(String(300))
    plan: Mapped[str] = mapped_column(String(10), index=True)  # direct | regular | unknown
    option: Mapped[str] = mapped_column(String(10), index=True)  # growth | idcw | bonus | unknown
    option_detail: Mapped[str | None] = mapped_column(String(80))
    scheme_type: Mapped[str] = mapped_column(String(40))
    asset_class: Mapped[str] = mapped_column(String(30), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    raw_category: Mapped[str | None] = mapped_column(String(160))
    isin_growth: Mapped[str | None] = mapped_column(String(12), index=True)
    isin_reinvest: Mapped[str | None] = mapped_column(String(12))
    launch_date: Mapped[date | None] = mapped_column(Date)
    variant_key: Mapped[str | None] = mapped_column(String(300), index=True)
    twin_scheme_code: Mapped[int | None] = mapped_column(Integer)
    latest_nav: Mapped[float | None] = mapped_column(Float)
    latest_nav_date: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    tracked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    history_start: Mapped[date | None] = mapped_column(Date)
    history_end: Mapped[date | None] = mapped_column(Date)
    history_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    history_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class NavDaily(Base):
    """One row per scheme per NAV date. NAVs are stored as floats (AMFI publishes 4 decimals)."""

    __tablename__ = "nav_daily"
    __table_args__ = {"sqlite_with_rowid": False}  # the primary key *is* the table: about half the disk space

    scheme_code: Mapped[int] = mapped_column(ForeignKey("mf_schemes.scheme_code"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    nav: Mapped[float] = mapped_column(Float)


# ---------------------------------------------------------------------------
# Stocks, daily prices, trade ideas, backtests, paper trading (doc 02 §3, §4, §7, §9)
# ---------------------------------------------------------------------------


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(40), unique=True)  # NSE trading symbol, e.g. RELIANCE
    groww_symbol: Mapped[str] = mapped_column(String(60))  # e.g. NSE-RELIANCE
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    series: Mapped[str | None] = mapped_column(String(4))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    in_universe: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    universe_rank: Mapped[int | None] = mapped_column(Integer)
    median_traded_value: Mapped[float | None] = mapped_column(Float)
    history_start: Mapped[date | None] = mapped_column(Date)
    history_end: Mapped[date | None] = mapped_column(Date)
    history_error: Mapped[str | None] = mapped_column(Text)
    history_complete: Mapped[bool] = mapped_column(Boolean, default=False)  # full download done (a later start = listing date)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class PriceDaily(Base):
    __tablename__ = "price_daily"
    __table_args__ = {"sqlite_with_rowid": False}

    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)  # Groww sometimes omits recent opens
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger)


class IndexDaily(Base):
    __tablename__ = "index_daily"
    __table_args__ = {"sqlite_with_rowid": False}

    symbol: Mapped[str] = mapped_column(String(40), primary_key=True)  # e.g. NIFTY, INDIAVIX; "BSE:RELIANCE" = BSE stock close for the ticker
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)  # Groww leaves it empty for BSE stocks and recent sessions
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)


class Recommendation(Base):
    """Every idea NiveshMitra ever showed. Append-only: database triggers refuse deletes and edits (except status)."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    engine: Mapped[str] = mapped_column(String(20))  # swing | stock_lt | mf
    setup: Mapped[str | None] = mapped_column(String(40))
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    scheme_code: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[str | None] = mapped_column(String(10))
    entry_low: Mapped[float | None] = mapped_column(Float)
    entry_high: Mapped[float | None] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float)
    target: Mapped[float | None] = mapped_column(Float)
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    qty: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[float | None] = mapped_column(Float)
    rationale_json: Mapped[dict | None] = mapped_column(JSON)
    risks_json: Mapped[list | None] = mapped_column(JSON)
    groww_steps_json: Mapped[list | None] = mapped_column(JSON)
    strategy_version_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_versions.id"))
    data_as_of: Mapped[date | None] = mapped_column(Date)
    for_session: Mapped[date | None] = mapped_column(Date, index=True)
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | expired | taken


class SetupBacktest(Base):
    __tablename__ = "setup_backtests"

    id: Mapped[int] = mapped_column(primary_key=True)
    setup: Mapped[str] = mapped_column(String(40), index=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    capital: Mapped[float] = mapped_column(Float)
    universe_size: Mapped[int] = mapped_column(Integer)
    stats_json: Mapped[dict] = mapped_column(JSON)
    allowed: Mapped[bool] = mapped_column(Boolean)
    verdict: Mapped[str] = mapped_column(Text)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), default="trading")
    start_capital: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("paper_accounts.id"), index=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("recommendations.id"))
    instrument_id: Mapped[int] = mapped_column(ForeignKey("instruments.id"))
    setup: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), index=True)  # pending | open | closed | missed | cancelled
    qty: Mapped[int] = mapped_column(Integer)
    entry_low: Mapped[float] = mapped_column(Float)
    entry_high: Mapped[float] = mapped_column(Float)
    stop: Mapped[float] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    max_hold_days: Mapped[int] = mapped_column(Integer)
    placed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    for_session: Mapped[date] = mapped_column(Date)
    entry_date: Mapped[date | None] = mapped_column(Date)
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_date: Mapped[date | None] = mapped_column(Date)
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_reason: Mapped[str | None] = mapped_column(String(20))
    days_held: Mapped[int] = mapped_column(Integer, default=0)
    charges_json: Mapped[dict | None] = mapped_column(JSON)
    net_pnl: Mapped[float | None] = mapped_column(Float)
    r_multiple: Mapped[float | None] = mapped_column(Float)


# ---------------------------------------------------------------------------
# Mutual fund facts and scores (doc 02 §3, §7)
# ---------------------------------------------------------------------------


class MfSchemeFacts(Base):
    """Monthly snapshot per scheme (as_of = first day of the month): expense ratio now, AUM/manager later."""

    __tablename__ = "mf_scheme_facts"

    scheme_code: Mapped[int] = mapped_column(ForeignKey("mf_schemes.scheme_code"), primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    ter: Mapped[float | None] = mapped_column(Float)  # fraction a year: 0.0069 = 0.69%
    fee: Mapped[float | None] = mapped_column(Float)  # the fund house's own part of ter (base expense ratio)
    ter_date: Mapped[date | None] = mapped_column(Date)
    aum_cr: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40), default="amfi_ter")
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ScoreRun(Base):
    __tablename__ = "score_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    engine: Mapped[str] = mapped_column(String(20), index=True)  # mf | stock_lt
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    run_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    data_as_of: Mapped[date] = mapped_column(Date)
    universe_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="ok")


class FundScore(Base):
    __tablename__ = "fund_scores"

    run_id: Mapped[int] = mapped_column(ForeignKey("score_runs.id"), primary_key=True)
    scheme_code: Mapped[int] = mapped_column(ForeignKey("mf_schemes.scheme_code"), primary_key=True, index=True)
    peer_group: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(20))
    total: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    peers: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(10))
    coverage: Mapped[float] = mapped_column(Float)
    components_json: Mapped[dict | None] = mapped_column(JSON)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    reasons_for_json: Mapped[list | None] = mapped_column(JSON)
    reasons_against_json: Mapped[list | None] = mapped_column(JSON)
    unranked_reason: Mapped[str | None] = mapped_column(Text)


class NewsBrief(Base):
    """Only the derived tone of each news pulse (not Trendlyne's text), kept to score news tone against the market's move."""

    __tablename__ = "news_briefs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    session_date: Mapped[date] = mapped_column(Date, index=True)  # the trading session the brief was written for
    overall: Mapped[str] = mapped_column(String(10))  # positive | negative | mixed | neutral | unrated
    positive: Mapped[int] = mapped_column(Integer, default=0)
    negative: Mapped[int] = mapped_column(Integer, default=0)
    neutral: Mapped[int] = mapped_column(Integer, default=0)
    headlines: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(10))  # claude | template
