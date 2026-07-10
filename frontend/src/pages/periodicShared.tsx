import { fmtMoney, fmtPct } from '../api';

export interface PeriodAuto {
  start: string;
  end: string;
  return_pct: number;
  max_drawdown_pct: number;
  end_nav: number;
  trade_count: number;
  closed_rounds: number;
  round_pnl: number;
  win_rounds: number;
}

export function isoWeek(d: Date): [number, number] {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return [date.getUTCFullYear(), week];
}

export function AutoStats({ auto }: { auto: PeriodAuto }) {
  return (
    <div className="periodic-stats">
      <StatItem label="区间收益" tone={auto.return_pct >= 0 ? 'pos' : 'neg'} value={fmtPct(auto.return_pct)} />
      <StatItem label="区间最大回撤" value={fmtPct(auto.max_drawdown_pct, false)} />
      <StatItem label="期末净值" value={auto.end_nav.toFixed(4)} />
      <StatItem label="交易 / 清仓回合" value={`${auto.trade_count} / ${auto.closed_rounds}`} />
      <StatItem label="回合盈亏" tone={auto.round_pnl >= 0 ? 'pos' : 'neg'} value={`¥${fmtMoney(auto.round_pnl)}`} />
    </div>
  );
}

function StatItem({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  return (
    <div className="periodic-stat">
      <div className="periodic-stat-label">{label}</div>
      <div className={`periodic-stat-value${tone ? ` ${tone}` : ''}`}>{value}</div>
    </div>
  );
}

export function PeriodicField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="periodic-field">
      <span className="periodic-field-label">{label}</span>
      <textarea
        className="periodic-textarea"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  );
}

export function PrintTextBlock({ label, text }: { label: string; text: string }) {
  if (!text?.trim()) return null;
  return (
    <div className="print-text-block">
      <div className="print-text-label">{label}</div>
      <div className="print-text-body">{text}</div>
    </div>
  );
}

export function AutoStatsPrint({ auto }: { auto: PeriodAuto }) {
  return (
    <div className="stat-row">
      <div className="stat-item">
        <div className="stat-label">区间收益</div>
        <div className={`stat-value${auto.return_pct >= 0 ? ' pos' : ' neg'}`}>{fmtPct(auto.return_pct)}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">区间最大回撤</div>
        <div className="stat-value">{fmtPct(auto.max_drawdown_pct, false)}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">期末净值</div>
        <div className="stat-value">{auto.end_nav.toFixed(4)}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">交易 / 清仓回合</div>
        <div className="stat-value">{auto.trade_count} / {auto.closed_rounds}</div>
      </div>
      <div className="stat-item">
        <div className="stat-label">回合盈亏</div>
        <div className={`stat-value${auto.round_pnl >= 0 ? ' pos' : ' neg'}`}>¥{fmtMoney(auto.round_pnl)}</div>
      </div>
    </div>
  );
}

export function PrintDocHeader({ username, title, subtitle }: { username: string; title: string; subtitle: string }) {
  const meta = username.trim() ? `${username.trim()} · ${subtitle}` : subtitle;
  return (
    <div className="print-doc-header">
      <h1>{title}</h1>
      <div className="print-doc-meta">{meta}</div>
    </div>
  );
}

export function WeeklyPrintBody({
  username, year, week, periodLabel, auto,
  market_review, right_things, wrong_things, next_strategy,
}: {
  username: string;
  year: number;
  week: number;
  periodLabel: string;
  auto: PeriodAuto;
  market_review: string;
  right_things: string;
  wrong_things: string;
  next_strategy: string;
}) {
  return (
    <>
      <PrintDocHeader username={username} title="Trading MS 周复盘" subtitle={`${year} 第 ${week} 周 · ${periodLabel}`} />
      <AutoStatsPrint auto={auto} />
      <PrintTextBlock label="本周盘面回顾" text={market_review} />
      <PrintTextBlock label="本周做对的事" text={right_things} />
      <PrintTextBlock label="本周做错的事" text={wrong_things} />
      <PrintTextBlock label="下周策略" text={next_strategy} />
    </>
  );
}

export function MonthlyPrintBody({
  username, year, month, periodLabel, auto, node_state,
  system_iteration, next_goal,
}: {
  username: string;
  year: number;
  month: number;
  periodLabel: string;
  auto: PeriodAuto;
  node_state: { lit_count: number; node_count: number; nav: number };
  system_iteration: string;
  next_goal: string;
}) {
  return (
    <>
      <PrintDocHeader username={username} title="Trading MS 月复盘" subtitle={`${year} 年 ${month} 月 · ${periodLabel}`} />
      <AutoStatsPrint auto={auto} />
      <div className="print-text-body" style={{ marginBottom: 12 }}>
        节点进度：已点亮 {node_state.lit_count} / {node_state.node_count} · 当前净值 {node_state.nav.toFixed(4)}
      </div>
      <PrintTextBlock label="体系迭代" text={system_iteration} />
      <PrintTextBlock label="下月目标" text={next_goal} />
    </>
  );
}
