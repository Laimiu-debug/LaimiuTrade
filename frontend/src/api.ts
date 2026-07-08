const BASE = '';

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const resp = await fetch(BASE + url, {
    method,
    headers: body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const data = await resp.json();
      detail = data.detail ?? JSON.stringify(data);
    } catch { /* keep statusText */ }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body),
  put: <T>(url: string, body?: unknown) => request<T>('PUT', url, body),
  del: <T>(url: string) => request<T>('DELETE', url),
};

// ---------- 类型 ----------

export interface NavState {
  nav: number;
  assets: number;
  shares: number;
  day: string | null;
  lit_levels: number[];
  lit_count: number;
  next_level: number | null;
  next_threshold: number | null;
  next_gap_pct: number | null;
  next_assets_target?: number | null;
  max_nav: number;
  drawdown_pct: number;
  node_count: number;
  wave_pct: number;
  leg_progress_pct: number;
}

export interface CurvePoint {
  date: string;
  nav: number;
  assets: number;
  drawdown_pct: number;
}

export interface TradeRow {
  id: number;
  trade_date: string;
  code: string;
  name: string;
  side: 'buy' | 'sell';
  price: number;
  qty: number;
  fees: number;
  amount: number;
  note: string;
  source: string;
}

export interface RoundRow {
  code: string;
  name: string;
  start_date: string;
  end_date: string | null;
  status: 'closed' | 'open' | 'anomaly';
  position: number;
  buy_amount: number;
  sell_amount: number;
  fees: number;
  pnl: number | null;
  pnl_pct: number | null;
  trades: { id: number; date: string; side: string; price: number; qty: number; fees: number }[];
}

export interface RoundStats {
  total_rounds: number;
  open_rounds: number;
  win_count: number;
  lose_count: number;
  win_rate: number | null;
  avg_win: number;
  avg_loss: number;
  profit_loss_ratio: number | null;
  max_win_streak: number;
  max_lose_streak: number;
  total_pnl: number;
}

export interface ScoreEntry {
  ai?: number | null;
  final?: number | null;
  comment?: string;
}

export interface WatchItem {
  code: string;
  name: string;
  condition: string;
  action: string;
}

export interface DailyReview {
  review_date: string;
  market_observation: string;
  decision_review: string;
  mistakes: string;
  images: string[];
  scores: Record<string, ScoreEntry>;
  ai_summary: string;
  next_market_forecast: string;
  next_watchlist: WatchItem[];
  next_position_plan: string;
  next_risk_plan: string;
  trades: { id: number; code: string; name: string; side: string; price: number; qty: number; fees: number }[];
  snapshot: number | null;
}

export interface FlashCard {
  id: number;
  content: string;
  tags: string;
  created_at: string;
}

export interface NodeInfo {
  level: number;
  threshold: number;
  assets_equiv: number | null;
  lit: boolean;
}

export interface NodeTiming {
  level: number;
  first_lit: string;
  days_taken: number | null;
}

export interface Overview {
  state: NavState;
  curve: CurvePoint[];
  max_drawdown_pct: number;
  weekly_returns: { period: string; return_pct: number; end_nav: number }[];
  monthly_returns: { period: string; return_pct: number; end_nav: number }[];
  round_stats: RoundStats;
  node_timing: NodeTiming[];
  missing_reviews: string[];
}

export const SCORE_DIMS: Record<string, string> = {
  position: '仓位控制',
  drawdown: '回撤控制',
  discipline: '计划执行力',
  entry: '买点质量',
  exit: '卖点质量',
  emotion: '情绪管理',
};

export const fmtMoney = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 });

export const fmtPct = (v: number | null | undefined, signed = true) =>
  v === null || v === undefined ? '—' : `${signed && v > 0 ? '+' : ''}${v.toFixed(2)}%`;

export const today = () => new Date().toISOString().slice(0, 10);
