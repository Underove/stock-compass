import type {
  Alert,
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
  PortfolioMover,
  PortfolioOneliner,
  PortfolioSnapshot,
  TradeDiagnose,
  SavedFilter,
  ScreenerItem,
  ScreenerParams,
  SearchResult,
  ServiceInfo,
  ShortSellingData,
  SimilarItem,
  Source,
  StockCommentary,
  StockPrice,
  Trade,
  TradeSummaryItem,
  TradingFlowItem,
  UploadResult,
  UploadSummary,
  UserProfile,
  WatchStock,
  CompareStock,
  CompareResponse,
  WatchlistItem,
} from "./types";

export type { Alert as PriceAlert } from "./types"; // 하위 호환
export type { CompareStock, CompareResponse };

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

export type StockInsight = { text: string; tone: "positive" | "negative" | "neutral" };

export async function fetchPortfolioInsights(): Promise<Record<string, StockInsight>> {
  try {
    const data = await getJSON<{ insights: Record<string, StockInsight> }>("/api/portfolio/insights");
    return data.insights ?? {};
  } catch {
    return {};
  }
}

export async function fetchTradeDiagnose(force = false): Promise<TradeDiagnose | null> {
  try {
    return await getJSON<TradeDiagnose>(`/api/trades/diagnose${force ? "?force=true" : ""}`);
  } catch {
    return null;
  }
}

export async function fetchPortfolioOneliner(force = false): Promise<PortfolioOneliner | null> {
  try {
    return await getJSON<PortfolioOneliner>(`/api/portfolio/oneliner${force ? "?force=true" : ""}`);
  } catch {
    return null;
  }
}

export async function fetchPortfolioMovers(): Promise<PortfolioMover[]> {
  try {
    const data = await getJSON<{ movers: PortfolioMover[] }>("/api/portfolio/movers");
    return data.movers ?? [];
  } catch {
    return [];
  }
}

export const ask = (question: string, n_chunks = 5) =>
  postJSON<{ answer: string; sources: Source[]; companies_synced: CompanySynced[] }>(
    "/api/ask",
    { question, n_chunks },
  );

export type AskStreamEvent =
  | { type: "metadata"; sources: Source[]; companies_synced: CompanySynced[] }
  | { type: "token"; text: string }
  | { type: "done" }
  | { type: "error"; message: string };

export async function* askStream(
  question: string,
  n_chunks = 5,
  signal?: AbortSignal,
): AsyncGenerator<AskStreamEvent, void, void> {
  const res = await fetch(`${API_BASE}/api/ask/stream`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ question, n_chunks }),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `요청 실패 (HTTP ${res.status})`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sepIdx;
    while ((sepIdx = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sepIdx);
      buffer = buffer.slice(sepIdx + 2);
      let event = "message";
      let dataLine = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (!dataLine) continue;
      let parsed: { sources?: Source[]; companies_synced?: CompanySynced[]; text?: string; message?: string };
      try { parsed = JSON.parse(dataLine); } catch { continue; }
      if (event === "metadata") {
        yield { type: "metadata", sources: parsed.sources ?? [], companies_synced: parsed.companies_synced ?? [] };
      } else if (event === "token") {
        yield { type: "token", text: parsed.text ?? "" };
      } else if (event === "done") {
        yield { type: "done" };
      } else if (event === "error") {
        yield { type: "error", message: parsed.message ?? "알 수 없는 오류" };
      }
    }
  }
}

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

export async function getUploadOriginalUrl(upload_id: string): Promise<string | null> {
  const res = await fetch(`${API_BASE}/api/uploads/${upload_id}/original`, { headers: authHeaders() });
  if (!res.ok) return null;
  const data = await res.json();
  return data.url ?? null;
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
  const res = await fetch(`${API_BASE}/api/portfolio/${stock_code}`, { method: "DELETE", headers: authHeaders() });
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
    headers: authHeaders({ "Content-Type": "application/json" }),
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
  const res = await fetch(`${API_BASE}/api/watchlist/${stock_code}`, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) throw new Error("삭제 실패");
}

// ─── AI 브리핑 ────────────────────────────────────────────────────────────────

export async function fetchPortfolioBriefing(force = false): Promise<PortfolioBriefing> {
  return getJSON(`/api/portfolio/briefing${force ? "?force=true" : ""}`);
}

export async function fetchStockPrice(stock_code: string): Promise<StockPrice> {
  return getJSON<StockPrice>(`/api/portfolio/price/${stock_code}`);
}

export async function fetchChartData(stock_code: string, days = 90, interval?: "5m" | "1d"): Promise<Candle[]> {
  const qs = interval
    ? `interval=${interval}`
    : `days=${days}`;
  const data = await getJSON<{ candles: Candle[] }>(
    `/api/portfolio/chart/${stock_code}?${qs}`,
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

export async function fetchAlerts(): Promise<Alert[]> {
  const data = await getJSON<{ alerts: Alert[] }>("/api/notifications/alerts");
  return data.alerts;
}

export async function markAlertsRead(ids: string[]): Promise<void> {
  await postJSON("/api/notifications/alerts/read", { ids });
}

export async function deleteAlert(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/notifications/alerts/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function fetchAlertWatch(): Promise<WatchStock[]> {
  const data = await getJSON<{ items: WatchStock[] }>("/api/notifications/watch");
  return data.items;
}

export async function addAlertWatch(stock_code: string, corp_name: string): Promise<void> {
  await postJSON("/api/notifications/watch", { stock_code, corp_name });
}

export async function removeAlertWatch(stock_code: string): Promise<void> {
  await fetch(`${API_BASE}/api/notifications/watch/${encodeURIComponent(stock_code)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function fetchPremarketNews(): Promise<PremarketNews | null> {
  const data = await getJSON<{ cached: PremarketNews | null }>("/api/notifications/premarket-news");
  return data.cached;
}

export async function generatePremarketNews(): Promise<PremarketNews | null> {
  const data = await postJSON<{ cached: PremarketNews | null }>("/api/notifications/premarket-news/generate", {});
  return data.cached;
}

export async function fetchPortfolioBriefingCached(): Promise<import("./types").PortfolioBriefing | null> {
  const data = await getJSON<{ cached: import("./types").PortfolioBriefing | null }>("/api/notifications/briefing-cache");
  return data.cached;
}

export async function saveNote(stock_code: string, note: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/portfolio/notes/${stock_code}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ note }),
  });
  if (!res.ok) throw new Error("메모 저장 실패");
}

// ─── 매매일지 ────────────────────────────────────────────────────────────────

export async function fetchTrades(params?: {
  limit?: number;
  offset?: number;
  stock_code?: string;
}): Promise<{ trades: Trade[]; total: number }> {
  const qs = new URLSearchParams();
  if (params?.limit != null) qs.set("limit", String(params.limit));
  if (params?.offset != null) qs.set("offset", String(params.offset));
  if (params?.stock_code) qs.set("stock_code", params.stock_code);
  return getJSON(`/api/trades${qs.toString() ? `?${qs}` : ""}`);
}

export async function updateTradeMemo(tradeId: number, memo: string): Promise<void> {
  await postJSON(`/api/trades/${tradeId}/memo`, { memo });
}

export async function fetchTradeSummary(): Promise<{ items: TradeSummaryItem[] }> {
  return getJSON("/api/trades/summary");
}

export async function fetchPortfolioSnapshots(days = 90): Promise<{ snapshots: PortfolioSnapshot[] }> {
  return getJSON(`/api/portfolio/snapshots?days=${days}`);
}

export async function deleteTrade(tradeId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/api/trades/${tradeId}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error("삭제 실패");
}

export async function editTrade(
  tradeId: number,
  trade_type: "buy" | "sell" | "edit",
  quantity: number,
  price: number,
  buy_price?: number | null,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/trades/${tradeId}`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ trade_type, quantity, price, buy_price: buy_price ?? null }),
  });
  if (!res.ok) throw new Error("수정 실패");
}

// ─── 투자 성향 프로필 ─────────────────────────────────────────────────────────

export async function getProfile(): Promise<UserProfile> {
  return getJSON<UserProfile>("/api/profile");
}

export async function updateProfile(
  data: Partial<Pick<UserProfile, "risk_level" | "horizon" | "sectors">>,
): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/api/profile`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || `요청 실패 (HTTP ${res.status})`);
  }
  return res.json();
}

// ─── 스크리너 ──────────────────────────────────────────────────────────────

export async function screenStocks(params: ScreenerParams): Promise<ScreenerItem[]> {
  const res = await fetch(`${API_BASE}/api/screener`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`스크리닝 실패 (HTTP ${res.status})`);
  return res.json();
}

export async function getSimilarStocks(stockCode: string): Promise<SimilarItem[]> {
  return getJSON<SimilarItem[]>(`/api/screener/similar/${stockCode}`);
}

export async function getSavedFilters(): Promise<SavedFilter[]> {
  return getJSON<SavedFilter[]>("/api/screener/filters");
}

export async function saveFilter(
  name: string,
  params: ScreenerParams,
): Promise<{ id: number; name: string }> {
  const res = await fetch(`${API_BASE}/api/screener/filters`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ name, ...params }),
  });
  if (!res.ok) throw new Error(`필터 저장 실패 (HTTP ${res.status})`);
  return res.json();
}

export async function deleteFilter(id: number): Promise<void> {
  await fetch(`${API_BASE}/api/screener/filters/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function fetchCompare(
  codeA: string,
  codeB: string,
  period: "1m" | "3m" | "6m" | "1y",
): Promise<CompareResponse> {
  return getJSON<CompareResponse>(`/api/compare?codes=${codeA},${codeB}&period=${period}`);
}
