import type {
  AnalysisResult,
  Candle,
  CompanySynced,
  DisclosureItem,
  FactcheckResult,
  FundamentalData,
  MarketIndex,
  MarketStatus,
  NewsItem,
  PortfolioBriefing,
  PortfolioItem,
  SearchMatch,
  SearchResult,
  ServiceInfo,
  ShortSellingData,
  Source,
  StockCommentary,
  StockPrice,
  TradingFlowItem,
  UploadResult,
  UploadSummary,
  WatchlistItem,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

let _token: string | null = null;

export async function initAuth() {
  try {
    const res = await fetch("/api/token");
    if (res.ok) {
      const data = await res.json();
      _token = data.token;
    }
  } catch { /* 무시 */ }
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  return {
    ...(extra ?? {}),
    ...(_token ? { Authorization: `Bearer ${_token}` } : {}),
  };
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `요청 실패 (HTTP ${res.status})`);
  }
  return res.json();
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `요청 실패 (HTTP ${res.status})`);
  }
  return res.json();
}

export async function fetchServiceInfo(): Promise<ServiceInfo> {
  const res = await fetch(`${API_BASE}/`);
  if (!res.ok) throw new Error(`서비스 연결 실패 (HTTP ${res.status})`);
  return res.json();
}

export async function uploadFile(file: File): Promise<UploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `업로드 실패 (HTTP ${res.status})`);
  }
  return res.json();
}

export const search = (query: string, n_results = 5) =>
  postJSON<{ query: string; matches: SearchMatch[] }>("/api/search", {
    query,
    n_results,
  });

export const ask = (question: string, n_chunks = 5) =>
  postJSON<{ answer: string; sources: Source[]; companies_synced: CompanySynced[] }>(
    "/api/ask",
    { question, n_chunks },
  );

export const runFactcheck = (upload_id: string) =>
  postJSON<FactcheckResult>("/api/factcheck/run", { upload_id });

export async function deleteUpload(upload_id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/uploads/${upload_id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("삭제 실패");
}

export async function listUploads(): Promise<UploadSummary[]> {
  const res = await fetch(`${API_BASE}/api/uploads`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.uploads ?? [];
}

// ─── 포트폴리오 ───────────────────────────────────────────────────────────────

export async function listPortfolio(): Promise<PortfolioItem[]> {
  const data = await getJSON<{ items: PortfolioItem[] }>("/api/portfolio");
  return data.items;
}

export async function addPortfolioItem(item: PortfolioItem): Promise<void> {
  await postJSON("/api/portfolio", item);
}

export async function removePortfolioItem(stock_code: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/portfolio/${stock_code}`, { method: "DELETE" });
  if (!res.ok) throw new Error("삭제 실패");
}

export async function updatePortfolioItem(
  stock_code: string,
  buy_price: number,
  quantity: number,
  target_price?: number,
  stop_loss?: number,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/portfolio/${stock_code}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ buy_price, quantity, target_price: target_price ?? null, stop_loss: stop_loss ?? null }),
  });
  if (!res.ok) throw new Error("수정 실패");
}

// ─── 시장 지수 ────────────────────────────────────────────────────────────────

export async function fetchMarketIndices(): Promise<{ indices: Record<string, MarketIndex>; market_status: MarketStatus }> {
  return getJSON("/api/market/indices");
}

// ─── 관심종목 ─────────────────────────────────────────────────────────────────

export async function listWatchlist(): Promise<WatchlistItem[]> {
  const data = await getJSON<{ items: WatchlistItem[] }>("/api/watchlist");
  return data.items;
}

export async function addWatchlistItem(item: WatchlistItem): Promise<void> {
  await postJSON("/api/watchlist", item);
}

export async function removeWatchlistItem(stock_code: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/watchlist/${stock_code}`, { method: "DELETE" });
  if (!res.ok) throw new Error("삭제 실패");
}

// ─── AI 브리핑 ────────────────────────────────────────────────────────────────

export async function fetchPortfolioBriefing(): Promise<PortfolioBriefing> {
  return getJSON("/api/portfolio/briefing");
}

export async function fetchStockPrice(stock_code: string): Promise<StockPrice> {
  return getJSON<StockPrice>(`/api/portfolio/price/${stock_code}`);
}

export async function fetchChartData(stock_code: string, days = 90): Promise<Candle[]> {
  const data = await getJSON<{ candles: Candle[] }>(
    `/api/portfolio/chart/${stock_code}?days=${days}`,
  );
  return data.candles;
}

export async function fetchCommentary(
  stock_code: string,
  corp_name: string,
): Promise<StockCommentary> {
  return getJSON<StockCommentary>(
    `/api/portfolio/commentary/${stock_code}?corp_name=${encodeURIComponent(corp_name)}`,
  );
}

export async function searchStock(q: string): Promise<SearchResult[]> {
  const data = await getJSON<{ results: SearchResult[] }>(
    `/api/portfolio/search?q=${encodeURIComponent(q)}`,
  );
  return data.results;
}

export async function fetchDisclosures(stock_code: string, days = 30): Promise<DisclosureItem[]> {
  const data = await getJSON<{ disclosures: DisclosureItem[] }>(
    `/api/portfolio/disclosures/${stock_code}?days=${days}`,
  );
  return data.disclosures;
}

export async function fetchPortfolioAlerts(): Promise<Record<string, number>> {
  const data = await getJSON<{ alerts: Record<string, number> }>("/api/portfolio/alerts");
  return data.alerts;
}

export const analyzePortfolio = (question?: string) =>
  postJSON<AnalysisResult>("/api/analyze", { question: question ?? "내 포트폴리오를 분석해줘" });

export async function fetchTechnical(stock_code: string): Promise<import("./types").TechnicalData> {
  return getJSON(`/api/portfolio/technical/${stock_code}`);
}

export async function fetchFundamental(stock_code: string): Promise<FundamentalData> {
  return getJSON(`/api/portfolio/fundamental/${stock_code}`);
}

export async function fetchTradingFlow(stock_code: string, days = 5): Promise<{ flow: TradingFlowItem[] }> {
  return getJSON(`/api/portfolio/trading-flow/${stock_code}?days=${days}`);
}

export async function fetchStockNews(stock_code: string, corp_name: string): Promise<{ news: NewsItem[] }> {
  return getJSON(`/api/portfolio/news/${stock_code}?corp_name=${encodeURIComponent(corp_name)}`);
}

export async function fetchShortSelling(stock_code: string, days = 5): Promise<ShortSellingData> {
  return getJSON(`/api/portfolio/short-selling/${stock_code}?days=${days}`);
}

export async function fetchNote(stock_code: string): Promise<string> {
  const data = await getJSON<{ note: string }>(`/api/portfolio/notes/${stock_code}`);
  return data.note;
}

// ─── 알림·브리핑 캐시·뉴스 요약 ──────────────────────────────────────────────

export type PriceAlert = {
  id: string;
  type: "target" | "stop_loss";
  stock_code: string;
  corp_name: string;
  current_price: number;
  trigger_price: number;
  message: string;
  created_at: string;
  read: boolean;
};

export type PremarketNewsSections = {
  date: string;
  headline: string;
  items: { corp_name: string; summary: string; tone: "positive" | "negative" | "neutral" }[];
  market_outlook: string;
};

export type PremarketNews = {
  summary: string;
  sections: PremarketNewsSections | null;
  generated_at: string;
  cached_date: string;
};

export async function fetchAlerts(): Promise<PriceAlert[]> {
  const data = await getJSON<{ alerts: PriceAlert[] }>("/api/notifications/alerts");
  return data.alerts;
}

export async function markAlertsRead(ids: string[]): Promise<void> {
  await postJSON("/api/notifications/alerts/read", { ids });
}

export async function fetchPremarketNews(): Promise<PremarketNews | null> {
  const data = await getJSON<{ cached: PremarketNews | null }>("/api/notifications/premarket-news");
  return data.cached;
}

export async function fetchPortfolioBriefingCached(): Promise<import("./types").PortfolioBriefing | null> {
  const data = await getJSON<{ cached: import("./types").PortfolioBriefing | null }>("/api/notifications/briefing-cache");
  return data.cached;
}

export async function saveNote(stock_code: string, note: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/portfolio/notes/${stock_code}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error("메모 저장 실패");
}
