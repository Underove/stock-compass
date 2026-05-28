export type BackendStatus = "checking" | "connected" | "error";
export type ServiceInfo = { service?: string; version?: string };

export type UploadResult = {
  upload_id: string;
  filename: string;
  size_bytes: number;
  char_count: number;
  chunk_count: number;
  vector_db_stored: boolean;
  vector_db_error: string | null;
  preview: string;
  first_chunks: string[];
};

export type UploadState =
  | { kind: "idle" }
  | { kind: "uploading" }
  | { kind: "done"; result: UploadResult }
  | { kind: "error"; message: string };

export type Source = { snippet: string; label: string; distance: number };

export type CompanySynced = { corp_name: string; stock_code: string };

export type ChatTurn = {
  id: number;
  question: string;
  answer: string | null;
  sources: Source[];
  error: string | null;
  companies_synced: CompanySynced[];
};

export type UploadSummary = {
  upload_id: string;
  filename: string;
  uploaded_at: string;
  chunk_count: number;
};

export type Verdict = "지지" | "모순" | "근거없음";

export type FactcheckClaim = {
  claim: string;
  verdict: Verdict | string;
  reasoning: string;
  sources: Source[];
};

export type FactcheckResult = {
  upload_id: string;
  signal: "red" | "yellow" | "green";
  score: number;
  companies_detected: { name: string; stock_code: string }[];
  claims: FactcheckClaim[];
};

export type FactcheckState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; result: FactcheckResult }
  | { kind: "error"; message: string };

// ─── 포트폴리오 ───────────────────────────────────────────────────────────────

export type PortfolioItem = {
  stock_code: string;
  corp_name: string;
  buy_price: number;
  quantity: number;
  target_price?: number;
  stop_loss?: number;
};

export type WatchlistItem = {
  stock_code: string;
  corp_name: string;
};

export type MarketIndex = {
  name: string;
  value: number;
  change: number;
  change_pct: number;
};

export type MarketStatus = {
  status: "open" | "closed" | "pre" | "after";
  label: string;
};

export type BriefingHighlight = {
  corp_name: string;
  status: string;
  note: string;
};

export type BriefingSections = {
  sentiment: "positive" | "negative" | "neutral";
  summary: string;
  highlights: (BriefingHighlight & { change_note?: string })[];
  action_items?: string[];
  watch: string;
  risk?: string;
};

export type PortfolioStats = {
  total_pnl_pct: number;
  stock_count: number;
  best: { corp_name: string; pnl_pct: number };
  worst: { corp_name: string; pnl_pct: number };
};

export type PortfolioBriefing = {
  briefing: string;
  sections: BriefingSections | null;
  generated_at: string;
  portfolio_stats: PortfolioStats | null;
};

export type StockPrice = {
  stock_code: string;
  current_price: number;
  change_pct: number;
  change_amount: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  date: string;
  session?: "open" | "pre" | "after" | "closed";
};

export type TradePattern = {
  label: string;
  detail: string;
  tone: "positive" | "negative" | "neutral";
};

export type TradeDiagnose = {
  diagnosis: string;
  patterns: TradePattern[];
  trade_count: number;
  generated_at: string;
};

export type PortfolioOneliner = {
  headline: string;
  tone: "positive" | "negative" | "neutral";
  generated_at: string;
};

export type PortfolioMover = {
  stock_code: string;
  corp_name: string;
  current_price: number;
  change_pct: number;
  sparkline: number[];
};

export type Candle = {
  time: string | number;  // string "YYYY-MM-DD" (daily) or number unix-seconds (intraday)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type CommentarySections = {
  sentiment?: "bullish" | "bearish" | "neutral";
  headline: string;
  trend: string;
  signal: string;
  note: string;
};

export type StockCommentary = {
  stock_code: string;
  corp_name: string;
  price: StockPrice;
  commentary: string;
  commentary_sections: CommentarySections | null;
};

export type SearchResult = {
  corp_code: string;
  corp_name: string;
  stock_code: string;
};

export type DisclosureItem = {
  report_nm: string;
  rcept_dt: string;
  flr_nm: string;
  rcept_no: string;
  url: string;
  ai_summary?: string | null;
};

export type AnalysisHolding = {
  corp_name: string;
  verdict: string;
  change_note?: string;
  comment: string;
};

export type AnalysisSource = {
  type: "dart" | "upload" | "news";
  label: string;
  snippet: string;
  url?: string | null;
  upload_id?: string | null;
  filename?: string | null;
};

export type AnalysisResult = {
  summary: string;
  holdings: AnalysisHolding[];
  action_items: string[];
  sources: AnalysisSource[];
  portfolio_count: number;
  upload_chunks: number;
  dart_chunks: number;
  news_loaded?: number;
};

export type CrossStatus = "golden" | "dead" | "above" | "below" | "none";

export type FundamentalData = {
  per: number | null;
  pbr: number | null;
  eps: number | null;
  div: number | null;
  bps: number | null;
  market_cap: number | null;
};

export type TradingFlowItem = {
  date: string;
  foreign_net: number;
  institution_net: number;
};

export type NewsItem = {
  title: string;
  description: string;
  url: string;
  date: string;
};

export type ShortSellingData = {
  ratio: number | null;
  trend: { date: string; ratio: number }[];
};

// ─── 매매일지 ────────────────────────────────────────────────────────────────

export type Trade = {
  id: number;
  stock_code: string;
  corp_name: string;
  trade_type: "buy" | "sell" | "edit";
  quantity: number;
  price: number;
  buy_price: number | null;
  memo: string | null;
  created_at: string;
};

export type TradeSummaryItem = {
  trade_id: number;
  date: string;
  corp_name: string;
  stock_code: string;
  quantity: number;
  sell_price: number;
  buy_price: number;
  realized_pnl: number;
};

export type PortfolioSnapshot = {
  snapshot_date: string;
  total_value: number;
  total_invested: number;
};

// ─── 투자 성향 프로필 ─────────────────────────────────────────────────────────

export type UserProfile = {
  username: string;
  risk_level: "aggressive" | "neutral" | "defensive";
  horizon: "short" | "mid" | "long";
  sectors: string[];
  ai_memo: string;
  updated_at: string;
};

export type TechnicalData = {
  current_price: number;
  ma5: number | null;
  ma20: number | null;
  ma60: number | null;
  cross_5_20: CrossStatus;
  cross_20_60: CrossStatus;
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  bb_upper: number | null;
  bb_mid: number | null;
  bb_lower: number | null;
  bb_position: number | null;
  support: number | null;
  resistance: number | null;
  high_52w: number;
  low_52w: number;
  pos_in_52w_range: number;
};

// ─── 스크리너 ──────────────────────────────────────────────────────────────

export type ScreenerParams = {
  sector?:         string;
  market_cap_min?: number;
  market_cap_max?: number;
  per_min?:        number;
  per_max?:        number;
  pbr_max?:        number;
  rsi_min?:        number;
  rsi_max?:        number;
  ma_status?:      "golden" | "dead" | "above" | "below";
};

export type ScreenerItem = {
  stock_code:    string;
  corp_name:     string;
  sector:        string;
  market_cap:    number;
  per:           number | null;
  pbr:           number | null;
  momentum_20d:  number;
  rsi:           number | null;
  ma_status:     string | null;
  has_ta:        number;
};

export type SimilarItem = {
  stock_code:   string;
  corp_name:    string;
  sector:       string;
  market_cap:   number;
  per:          number | null;
  momentum_20d: number;
};

export type SavedFilter = {
  id:         number;
  name:       string;
  params:     ScreenerParams;
  created_at: string;
};

// ─── 알림 고도화 ──────────────────────────────────────────────────────────────

export type AlertType =
  | "target"
  | "stop_loss"
  | "dart"
  | "volume_spike"
  | "rsi_overbought"
  | "rsi_oversold"
  | "golden_cross"
  | "dead_cross";

export type Alert = {
  id: string;
  type: AlertType;
  stock_code: string;
  corp_name: string;
  message: string;
  meta: Record<string, unknown> | null;
  created_at: string;
  read: boolean;
};

export type WatchStock = {
  stock_code: string;
  corp_name: string;
};

export type CompareStock = {
  stock_code: string;
  corp_name: string | null;
  sector: string | null;
  metrics: {
    market_cap: number | null;
    per: number | null;
    pbr: number | null;
    rsi: number | null;
    momentum_20d: number | null;
    volume_ratio: number | null;
    foreign_net_buy: number | null;
  };
  price_series: { date: string; close: number; return_pct: number }[];
};

export type CompareResponse = {
  stocks: [CompareStock, CompareStock];
  period: string;
};
