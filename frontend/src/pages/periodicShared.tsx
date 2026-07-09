import { fmtMoney, fmtPct } from '../api';
import { Stat } from '../components';

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
    <div className="row" style={{ justifyContent: 'space-between', marginBottom: 16 }}>
      <Stat small label="区间收益" tone={auto.return_pct >= 0 ? 'pos' : 'neg'} value={fmtPct(auto.return_pct)} />
      <Stat small label="区间最大回撤" value={fmtPct(auto.max_drawdown_pct, false)} />
      <Stat small label="期末净值" value={auto.end_nav.toFixed(4)} />
      <Stat small label="交易 / 清仓回合" value={`${auto.trade_count} / ${auto.closed_rounds}`} />
      <Stat small label="回合盈亏" tone={auto.round_pnl >= 0 ? 'pos' : 'neg'} value={`¥${fmtMoney(auto.round_pnl)}`} />
    </div>
  );
}
