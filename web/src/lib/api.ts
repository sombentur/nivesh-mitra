// Tiny client for the local backend. Every write carries the CSRF header the backend requires.

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      method,
      credentials: "same-origin",
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-NM-CSRF": "1" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Can't reach the NiveshMitra backend. Is it running?");
  }
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail))
        message = data.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, "")).join("; ");
    } catch {
      if (res.status >= 500) message = "The NiveshMitra backend isn't responding. Is it running?";
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body ?? {}),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body ?? {}),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export type SetupStatus = { configured: boolean; locked: boolean; google_client_id: string | null };
export type Me = { email: string; name: string | null; language: string };
export type Settings = {
  explanation_mode: "template" | "claude";
  claude_monthly_cap_inr: number;
  fundamentals_provider: "manual" | "eodhd";
  trendlyne_enabled: boolean;
  trendlyne_plan: "pro" | "max";
  language: "en" | "kn";
};
export type SecretStatus = {
  name: string;
  label: string;
  help: string;
  is_set: boolean;
  last4: string | null;
  updated_at: string | null;
};

// ---- Step 2: profile, onboarding, goals ----

export type Category = "conservative" | "moderate" | "aggressive";
export type Split = { core: number; satellite: number; trading: number };
export type Option = { value: string; label: string };

export type ProfileAnswers = {
  age: number;
  income_range: string;
  monthly_expenses: number;
  monthly_investable: number;
  emergency_savings: number;
  monthly_emi: number;
  horizon: string;
  fall_reaction: string;
  experience: string;
};

export type ProfileRules = {
  version: number;
  questions: {
    income_ranges: (Option & { low: number; high: number | null })[];
    horizons: Option[];
    fall_reactions: Option[];
    experience: Option[];
    goal_types: (Option & { inflation: number })[];
  };
  splits: Record<Category, Split>;
  limits: {
    trading_warn_above: number;
    trading_max: number;
    satellite_warn_above: number;
    core_warn_below: number;
    loosen_delay_hours: number;
  };
  emergency_fund: { target_months: number; trading_unlock_months: number };
  paper_trading_days: number;
  sebi_reality_check: { text: string; source: string; date: string }[];
};

export type Emergency = {
  target: number;
  current: number;
  months_covered: number;
  shortfall: number;
  status: "ok" | "building" | "missing";
  monthly_to_liquid: number;
  months_to_complete: number | null;
  first_action: string | null;
};

export type ProfileView = {
  id: number;
  created_at: string;
  review_due_on: string;
  review_due: boolean;
  rules_version: number;
  answers: ProfileAnswers;
  result: {
    capacity_score: number;
    capacity_category: Category;
    tolerance_category: Category;
    final_category: Category;
    reasons: { factor: string; points: number | null; text: string }[];
    overrides: string[];
    emergency: Emergency;
    default_split: Split;
    sanity_warnings: string[];
  };
  allocation: {
    target: Split;
    effective: Split;
    default: Split;
    is_user_override: boolean;
    warnings: string[];
    trading_locked: boolean;
    trading_lock_reasons: string[];
    pending: (Split & { effective_at: string; reason: string | null }) | null;
  };
  paper: { started_on: string | null; ends_on: string | null; days_left: number; complete: boolean };
};

export type OnboardingStatus = {
  profile_done: boolean;
  sebi_acknowledged: boolean;
  paper_started: boolean;
  complete: boolean;
};

export type GoalInput = {
  name: string;
  goal_type: string;
  target_amount_today: number;
  target_year: number;
  current_corpus?: number;
  priority?: number;
  inflation_rate?: number | null;
};

export type Goal = Required<Omit<GoalInput, "inflation_rate">> & {
  id: number;
  inflation_rate: number;
  years_away: number;
  target_amount_future: number;
};

// ---- Step 3: mutual fund data ----

export type FundBrief = {
  scheme_code: number;
  name: string;
  amc: string | null;
  asset_class: string;
  category: string;
  plan: string;
  option: string;
  latest_nav: number | null;
  latest_nav_date: string | null;
  tracked: boolean;
  score: FundScoreBrief | null;
};

export type FundScoreBrief = { total: number | null; rank: number | null; peers: number; confidence: string; peer_group: string };

export type FundScoring = {
  total: number | null;
  rank: number | null;
  peers: number;
  peer_group: string;
  model: "equity" | "index" | "debt" | "liquid";
  confidence: "high" | "medium" | "low" | "unranked";
  coverage: number;
  unranked_reason: string | null;
  components: Record<string, { value: number; percentile: number; weight: number }>;
  metrics: Record<string, number | null>;
  reasons_for: string[];
  reasons_against: string[];
  regular_cost_10y_on_5000: number | null;
  rules_version: number;
  as_of: string | null;
};

export type FundCategory = { asset_class: string; category: string; count: number };

export type FundDetail = FundBrief & {
  fund_name: string;
  option_detail: string | null;
  scheme_type: string;
  launch_date: string | null;
  isin: string | null;
  is_active: boolean;
  twin: FundBrief | null;
  scoring: FundScoring | null;
  ter_history: [string, number][];
  history: { status: "ready" | "not_downloaded" | "failed"; error: string | null; points: number };
  returns: { "1y": number | null; "3y": number | null; "5y": number | null; "10y": number | null; since_start: number | null; history_from: string | null };
  chart: [string, number][];
};

export type JobRunView = { status: string; started_at: string; finished_at: string | null; detail: string | null };

export type DataStatus = {
  nav: {
    latest_nav_date: string | null;
    fresh: boolean;
    active_schemes: number;
    tracked: number;
    synced: number;
    failed: number;
  };
  jobs: {
    name: string;
    label: string;
    running: boolean;
    progress: { done: number; total: number } | null;
    last_run: JobRunView | null;
    last_success: JobRunView | null;
    next_run_at: string | null;
  }[];
};

// ---- Practice trading ----

export type TradingIdea = {
  id: number;
  setup: string;
  setup_label: string;
  setup_plain: string;
  status: string;
  for_session: string;
  data_as_of: string;
  confidence: "high" | "medium" | "low";
  symbol: string;
  name: string;
  close: number;
  entry_low: number;
  entry_high: number;
  stop: number;
  target: number;
  hold_days: number;
  qty: number;
  amount: number;
  reward_risk: number;
  risk_amount: number;
  reward_amount: number;
  charges: number;
  breakeven_pct: number;
  reasons: string[];
  risks: string[];
  groww_steps: string[];
  backtest: { trades: number; win_rate: number; avg_r: number; profit_factor: number | null; avg_hold_days: number; max_losing_streak: number; period: [string, string] };
};

export type TradingOverview = {
  state: {
    capital: number;
    account_start_capital: number;
    realized_pnl: number;
    open_positions: number;
    max_open_positions: number;
    cooling_off_until: string | null;
    cooling_off_reason: string | null;
    loss_limit_hit: boolean;
    loss_limit_reason: string | null;
    latest_session: string | null;
  };
  ideas_status: { as_of: string; for_session: string | null; count: number; reason: string | null; at: string } | null;
  practice: { started_on: string | null; ends_on: string | null; days_left: number; complete: boolean };
  real_money_locked: string[];
  data: { latest_session: string | null; universe_size: number; prices_ok: boolean; prices_error: string | null };
};

export type PaperTradeView = {
  id: number;
  symbol: string;
  name: string;
  setup: string;
  status: "pending" | "open" | "closed" | "missed" | "cancelled";
  qty: number;
  entry_low: number;
  entry_high: number;
  stop: number;
  target: number;
  for_session: string;
  entry_date: string | null;
  entry_price: number | null;
  exit_date: string | null;
  exit_price: number | null;
  exit_reason: string | null;
  days_held: number;
  charges: number | null;
  net_pnl: number | null;
  r_multiple: number | null;
};

export type PaperSummary = {
  start_capital: number;
  started: string;
  equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  charges_paid: number;
  closed_trades: number;
  win_rate: number | null;
  avg_r: number | null;
  trades: PaperTradeView[];
};

export type SetupBacktestView = {
  setup: string;
  label: string;
  plain: string;
  enabled: boolean;
  tested: boolean;
  allowed: boolean;
  verdict: string;
  run_at: string | null;
  capital: number | null;
  universe_size: number | null;
  stats: { trades: number; win_rate?: number; avg_r?: number; avg_r_before_charges?: number; profit_factor?: number | null; avg_hold_days?: number; avg_charges?: number; max_losing_streak?: number; period?: [string, string] } | null;
  portfolio: { capital: number; trades_taken: number; final_equity: number; cagr: number; max_drawdown: number; ruined_on?: string | null } | null;
};

export type GrowwCheckPart = { ok: boolean; detail: string } | null;
export type GrowwCheck = { auth_method: "totp" | "secret" | null; login: GrowwCheckPart; portfolio: GrowwCheckPart; prices: GrowwCheckPart; history: GrowwCheckPart };

// ---- My plan ----

export type PlanFund = {
  scheme_code: number;
  name: string;
  category: string;
  score: number | null;
  rank: number | null;
  peers: number;
  confidence: string;
  ter: number | null;
  regular_cost_gap: number | null;
  rr5_med: number | null;
  rr3_med: number | null;
  maxdd_5y: number | null;
  reasons_for: string[];
  reasons_against: string[];
};

export type PlanGoal = {
  id: number;
  name: string;
  target_year: number;
  months_away: number;
  years_away: number;
  target_today: number;
  target_future: number;
  current_corpus: number;
  allocation: Record<string, number>;
  equity_share: number;
  rates: [number, number, number];
  sip_needed: { conservative: number; expected: number; optimistic: number };
  recommended_sip: number;
  affordable_now: number;
  funds: { slot: string; label: string; share: number; monthly: number; fund: PlanFund | null; regular_would_cost_10y: number | null }[];
  projection_if_recommended: [number, number, number];
};

export type Plan = {
  generated_at: string;
  scores_as_of: string;
  profile: string;
  budget: { investable: number; to_emergency_fund: number; for_mutual_funds: number; for_stocks: number; goals_need: number };
  emergency: {
    target: number;
    current: number;
    shortfall: number;
    monthly: number;
    months_to_complete: number | null;
    fund: PlanFund | null;
    groww_steps: string[];
  } | null;
  goals: PlanGoal[];
  sips: { fund: PlanFund; label: string; monthly_needed: number; monthly_affordable: number; goals: string[]; groww_steps: string[] }[];
  notes: string[];
  assumptions: Record<string, [number, number, number]>;
};

export type SipCalcResult = {
  mix: Record<string, number>;
  scenarios: { scenario: string; rate: number; value: number; invested: number }[];
  note: string;
};

// ---- Dashboard ----

export type MarketMood = {
  mood: "Positive" | "Mixed" | "Weak";
  tone: "good" | "warn" | "bad";
  reason: string;
  nifty: number;
  change_pct: number;
  as_of: string;
  vix: number | null;
  chart: [string, number][];
};

export type HorizonPick = {
  scheme_code: number;
  name: string;
  category: string;
  score: number | null;
  rank: number | null;
  peers: number;
  confidence: string;
  ter: number | null;
  fee: number | null;
  typical_1y: number | null;
  typical_3y: number | null;
  typical_5y: number | null;
  worst_fall: number | null;
  worst_month: number | null;
  reason: string | null;
};

export type Horizon = { key: "m3" | "m6" | "y1" | "y2" | "y3" | "y5"; label: string; why: string; picks: HorizonPick[] };

export type Dashboard = { market: MarketMood | null; horizons: Horizon[]; days?: DayStrip };

// ---- Market widgets ----

export type MarketSeries = {
  symbol: string;
  last: number;
  prev: number;
  change: number;
  change_pct: number;
  spark: number[];
  ret_1w: number | null;
  ret_1m: number | null;
  ret_3m: number | null;
  ret_1y: number | null;
  above_50: boolean;
  above_200: boolean;
  high_52w: number;
  low_52w: number;
  from_high: number | null;
  trend: "Uptrend" | "Downtrend" | "Sideways" | "New";
};

export type MarketIndex = MarketSeries & { label: string; as_of: string; exchange: "NSE" | "BSE"; sector?: string | null; key?: string | null };
export type MarketStock = MarketSeries & { name: string; rank: number | null; value_cr: number; avg_value_cr: number };
export type SnapList = "leaders" | "gainers" | "losers" | "active" | "highs";

export type MarketSnapshot = {
  as_of: string | null;
  live: boolean;
  market_open: boolean;
  updated_at: string;
  indices: MarketIndex[];
  sectors: MarketIndex[];
  breadth: { total: number; advancers: number; decliners: number; unchanged: number; above_50: number; above_200: number; near_high: number; near_low: number };
  stocks: Record<string, MarketStock>;
  lists: Record<SnapList, string[]>;
};

export type TickerItem = { symbol: string; label: string; last: number; change_pct: number; kind: "index" | "stock" };
// ---- Sector pages (the companies behind each sector tile) ----

export type SectorIndex = Pick<MarketSeries, "last" | "change" | "change_pct" | "spark" | "ret_1w" | "ret_1m" | "ret_3m" | "ret_1y" | "high_52w" | "low_52w" | "from_high" | "trend"> & {
  symbol: string;
  name: string;
  as_of: string;
};
export type SectorSummary = {
  companies: number;
  advancers: number;
  decliners: number;
  unchanged: number;
  avg_change_pct: number | null;
  best: { symbol: string; change_pct: number } | null;
  worst: { symbol: string; change_pct: number } | null;
};
type SectorCommon = { as_of: string | null; live: boolean; market_open: boolean; updated_at: string; checked: string; tracked: number };
export type SectorCard = { key: string; label: string; about: string; index: SectorIndex | null; summary: SectorSummary };
export type SectorOverview = SectorCommon & { sectors: SectorCard[]; unclassified: string[] };
export type SectorDetail = SectorCommon & {
  key: string;
  label: string;
  about: string;
  industries: { key: string; label: string }[];
  index: SectorIndex | null;
  history: [string, number][];
  summary: SectorSummary;
  groups: { industry: string; label: string; companies: MarketStock[] }[];
  others: { key: string; label: string }[];
};

export type TickerData = { live: boolean; market_open: boolean; as_of: string | null; updated_at: string; nse: TickerItem[]; bse: TickerItem[] };

export type IntradayStats = { trades: number; win_rate?: number; avg_r?: number; avg_r_before_charges?: number; avg_charges?: number; period?: [string, string] };
export type IntradaySetupView = {
  setup: string;
  label: string;
  plain: string;
  enabled: boolean;
  tested: boolean;
  allowed: boolean;
  verdict: string;
  run_at: string | null;
  capital: number | null;
  build: IntradayStats | null;
  test: IntradayStats | null;
  test_avg_r_at_1_lakh: number | null;
};

// ---- News pulse ----

export type NewsTone = "positive" | "negative" | "neutral";
export type NewsItem = {
  symbol: string;
  company: string;
  kind: string;
  title: string;
  description: string;
  source: string;
  url: string | null;
  published: string;
  role: "heavyweight" | "gainer" | "loser";
  change_pct: number | null;
  tone?: NewsTone;
  why?: string;
};
export type NewsPulse = {
  pulse: {
    fetched_at: string;
    session: string;
    source: "claude" | "template";
    note: string | null;
    brief_en: string;
    brief_kn: string | null;
    overall: "positive" | "negative" | "mixed" | "neutral" | "unrated";
    counts: Record<NewsTone, number>;
    companies: number;
    items: NewsItem[];
  } | null;
  scorecard: { days: number; agreed: number; min_days: number };
  claude: boolean;
  spend: { month: string; inr: number; calls: number; cap_inr: number };
  refreshing: boolean;
};

// ---- Trading calendar ----

export type IndexMove = { close: number; change_pct: number };
export type CalendarDay = {
  date: string;
  status: "trading" | "weekend" | "holiday" | "special";
  name: string | null;
  note: string | null;
  nifty: IndexMove | null;
  sensex: IndexMove | null;
  pnl: number | null;
  closed_trades: number;
  ideas: number;
  events: string[];
};
export type CalendarData = {
  today: string;
  latest_session: string | null;
  market: { state: "open" | "pre" | "closed"; next_open: string };
  holidays_known_until: string | null;
  days: CalendarDay[];
};

// ---- Refresh button ----

export type Freshness = {
  now: string;
  market_open: boolean;
  prices: { latest_session: string | null; expected_session: string; behind: boolean; updated_at: string | null; error: string | null };
  navs: { date: string | null };
  running: { name: string; label: string; progress: { done: number; total: number } | null }[];
  started?: string[];
};

// ---- Yesterday / Today / Tomorrow row ----

export type DayMover = { symbol: string; last: number; change_pct: number };
export type DayMarket = {
  nifty: IndexMove;
  sensex: IndexMove | null;
  advancers: number;
  decliners: number;
  stocks: number;
  gainers: DayMover[];
  losers: DayMover[];
};
export type PracticeTrade = {
  symbol: string;
  setup: string;
  entry_time: string;
  entry: number;
  exit_time: string;
  exit: number;
  exit_reason: "stop" | "target" | "time";
  qty: number;
  net_pnl: number;
  r: number;
};
export type IntradayRecap = {
  date: string;
  capital: number;
  stocks: number;
  filter_ok: boolean;
  setups: { key: string; label: string; signals: number; won: number; target: number; stopped: number; avg_r: number | null; avg_pnl: number | null }[];
  first_trades: PracticeTrade[];
  watchlist: { symbol: string; trigger: number; outcome: PracticeTrade | null }[];
};
export type WatchItem = {
  symbol: string;
  name: string;
  prev_close: number;
  prev_high: number;
  trigger: number;
  entry: number;
  stop: number;
  target: number;
  qty: number;
  amount: number;
  risk: number;
  reward: number;
  charges: number;
  traded_cr: number;
};
export type IntradayPlan = {
  session: string;
  based_on: string;
  capital: number;
  filter: { ok: boolean; nifty: number; average: number; days: number; as_of: string };
  verdict: "practice" | "stand_aside";
  setups: {
    key: string;
    label: string;
    plain: string;
    when: string;
    allowed: boolean;
    tested: { trades: number; win_rate: number; avg_r: number; avg_r_before_charges: number } | null;
  }[];
  watch_setup: string;
  watchlist: WatchItem[];
  rules: string[];
  max_trades: number;
  exit_time: string;
};
export type SkippedDay = { date: string; reason: string };
export type DayStrip = {
  previous: { date: string; is_yesterday: boolean; skipped: SkippedDay[]; market: DayMarket | null; recap: IntradayRecap | null };
  today: {
    date: string;
    status: "trading" | "weekend" | "holiday" | "special";
    name: string | null;
    note: string | null;
    market: { state: "open" | "pre" | "closed"; next_open: string };
    result: DayMarket | null;
    plan: IntradayPlan | null;
    recap: IntradayRecap | null;
  };
  next: { date: string; is_tomorrow: boolean; skipped: SkippedDay[]; plan: IntradayPlan | null; waiting_for_close: boolean };
  latest_session: string | null;
};
