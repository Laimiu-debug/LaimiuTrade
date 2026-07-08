import { useCallback, useEffect, useState } from 'react';
import { api, fmtMoney, fmtPct } from '../api';
import { Stat, useToast } from '../components';

interface PeriodAuto {
  start: string; end: string; return_pct: number; max_drawdown_pct: number;
  end_nav: number; trade_count: number; closed_rounds: number; round_pnl: number; win_rounds: number;
}
interface WeeklyData { year: number; week: number; right_things: string; wrong_things: string; next_strategy: string; auto: PeriodAuto }
interface MonthlyData { year: number; month: number; system_iteration: string; next_goal: string; auto: PeriodAuto; node_state: { lit_count: number; nav: number } }

function isoWeek(d: Date): [number, number] {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil(((date.getTime() - yearStart.getTime()) / 86400000 + 1) / 7);
  return [date.getUTCFullYear(), week];
}

function AutoStats({ auto }: { auto: PeriodAuto }) {
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

export default function Periodic() {
  const toast = useToast();
  const now = new Date();
  const [defYear, defWeek] = isoWeek(now);
  const [wk, setWk] = useState({ year: defYear, week: defWeek });
  const [mo, setMo] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [weekly, setWeekly] = useState<WeeklyData | null>(null);
  const [monthly, setMonthly] = useState<MonthlyData | null>(null);

  const loadWeekly = useCallback(() => {
    api.get<WeeklyData>(`/api/reviews/weekly/${wk.year}/${wk.week}`).then(setWeekly).catch(e => toast(String(e)));
  }, [wk, toast]);
  const loadMonthly = useCallback(() => {
    api.get<MonthlyData>(`/api/reviews/monthly/${mo.year}/${mo.month}`).then(setMonthly).catch(e => toast(String(e)));
  }, [mo, toast]);

  useEffect(loadWeekly, [loadWeekly]);
  useEffect(loadMonthly, [loadMonthly]);

  const shiftWeek = (delta: number) => {
    const monday = new Date(Date.UTC(wk.year, 0, 4));
    monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() || 7) + 1 + (wk.week - 1 + delta) * 7);
    const [y, w] = isoWeek(new Date(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate()));
    setWk({ year: y, week: w });
  };

  const shiftMonth = (delta: number) => {
    const m = mo.month + delta;
    if (m < 1) setMo({ year: mo.year - 1, month: 12 });
    else if (m > 12) setMo({ year: mo.year + 1, month: 1 });
    else setMo({ ...mo, month: m });
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">周·月复盘</h2>
          <div className="page-sub">拉远镜头，检视体系</div>
        </div>
        <button className="no-print" onClick={() => window.print()}>导出 PDF</button>
      </div>

      <div className="card">
        <h3 className="card-title">
          <span>周复盘 · {wk.year} 第 {wk.week} 周{weekly && <span className="muted">（{weekly.auto.start} ~ {weekly.auto.end}）</span>}</span>
          <span className="no-print">
            <button className="ghost" onClick={() => shiftWeek(-1)}>← 上一周</button>
            <button className="ghost" onClick={() => shiftWeek(1)}>下一周 →</button>
          </span>
        </h3>
        {weekly && (
          <>
            <AutoStats auto={weekly.auto} />
            <div className="grid grid-3">
              <label className="field"><span>本周做对的事</span>
                <textarea value={weekly.right_things} onChange={e => setWeekly({ ...weekly, right_things: e.target.value })} placeholder="坚持了什么原则？哪些操作值得复制？" />
              </label>
              <label className="field"><span>本周做错的事</span>
                <textarea value={weekly.wrong_things} onChange={e => setWeekly({ ...weekly, wrong_things: e.target.value })} placeholder="违背了什么纪律？亏损的根源？" />
              </label>
              <label className="field"><span>下周策略</span>
                <textarea value={weekly.next_strategy} onChange={e => setWeekly({ ...weekly, next_strategy: e.target.value })} placeholder="下周的仓位基调与主攻方向" />
              </label>
            </div>
            <button className="primary no-print" onClick={async () => {
              await api.put(`/api/reviews/weekly/${wk.year}/${wk.week}`, {
                right_things: weekly.right_things, wrong_things: weekly.wrong_things, next_strategy: weekly.next_strategy,
              });
              toast('周复盘已保存');
            }}>保存周复盘</button>
          </>
        )}
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card-title">
          <span>月复盘 · {mo.year} 年 {mo.month} 月</span>
          <span className="no-print">
            <button className="ghost" onClick={() => shiftMonth(-1)}>← 上一月</button>
            <button className="ghost" onClick={() => shiftMonth(1)}>下一月 →</button>
          </span>
        </h3>
        {monthly && (
          <>
            <AutoStats auto={monthly.auto} />
            <div className="muted" style={{ marginBottom: 14 }}>
              当前节点进度：已点亮 {monthly.node_state.lit_count} / 50 · 当前净值 {monthly.node_state.nav.toFixed(4)}
            </div>
            <div className="grid grid-2">
              <label className="field"><span>体系迭代 · 这个月对交易系统的思考与修正</span>
                <textarea value={monthly.system_iteration} onChange={e => setMonthly({ ...monthly, system_iteration: e.target.value })} placeholder="规则要不要改？哪条被证伪了？" />
              </label>
              <label className="field"><span>下月目标</span>
                <textarea value={monthly.next_goal} onChange={e => setMonthly({ ...monthly, next_goal: e.target.value })} placeholder="下个月的目标：不止是收益，还有行为目标" />
              </label>
            </div>
            <button className="primary no-print" onClick={async () => {
              await api.put(`/api/reviews/monthly/${mo.year}/${mo.month}`, {
                system_iteration: monthly.system_iteration, next_goal: monthly.next_goal,
              });
              toast('月复盘已保存');
            }}>保存月复盘</button>
          </>
        )}
      </div>
    </div>
  );
}
