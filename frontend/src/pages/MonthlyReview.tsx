import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../components';
import { AutoStats, type PeriodAuto } from './periodicShared';

interface MonthlyData {
  year: number;
  month: number;
  system_iteration: string;
  next_goal: string;
  auto: PeriodAuto;
  node_state: { lit_count: number; node_count: number; nav: number };
}

export default function MonthlyReview() {
  const toast = useToast();
  const now = new Date();
  const [mo, setMo] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [monthly, setMonthly] = useState<MonthlyData | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadMonthly = useCallback(() => {
    api.get<MonthlyData>(`/api/reviews/monthly/${mo.year}/${mo.month}`).then(setMonthly).catch(e => toast(String(e)));
  }, [mo, toast]);

  useEffect(loadMonthly, [loadMonthly]);

  const shiftMonth = (delta: number) => {
    const m = mo.month + delta;
    if (m < 1) setMo({ year: mo.year - 1, month: 12 });
    else if (m > 12) setMo({ year: mo.year + 1, month: 1 });
    else setMo({ ...mo, month: m });
  };

  const save = async (silent = false) => {
    if (!monthly) return;
    setSaving(true);
    try {
      await api.put(`/api/reviews/monthly/${mo.year}/${mo.month}`, {
        system_iteration: monthly.system_iteration,
        next_goal: monthly.next_goal,
      });
      if (!silent) toast('月复盘已保存');
    } catch (e) { toast(String(e)); } finally { setSaving(false); }
  };

  const aiReview = async () => {
    await save(true);
    setReviewing(true);
    try {
      const result = await api.post<Partial<MonthlyData>>(`/api/reviews/monthly/${mo.year}/${mo.month}/ai-review`);
      setMonthly(prev => prev ? {
        ...prev,
        system_iteration: result.system_iteration ?? prev.system_iteration,
        next_goal: result.next_goal ?? prev.next_goal,
      } : prev);
      toast('AI 月复盘草稿已生成，请核对后保存');
    } catch (e) { toast(String(e)); } finally { setReviewing(false); }
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">月复盘</h2>
          <div className="page-sub">审视体系进化与节点征途</div>
        </div>
        <div className="row no-print">
          <button onClick={() => window.print()}>导出 PDF</button>
          <button onClick={aiReview} disabled={reviewing}>{reviewing ? 'AI 复盘中…' : '✦ AI 复盘'}</button>
          <button className="primary" onClick={() => save()} disabled={saving}>{saving ? '保存中…' : '保存'}</button>
        </div>
      </div>

      <div className="print-only print-header">
        <h3>Trading MS 月复盘 · {mo.year} 年 {mo.month} 月</h3>
      </div>

      <div className="card">
        <h3 className="card-title">
          <span>{mo.year} 年 {mo.month} 月</span>
          <span className="no-print">
            <button className="ghost" onClick={() => shiftMonth(-1)}>← 上一月</button>
            <button className="ghost" onClick={() => shiftMonth(1)}>下一月 →</button>
          </span>
        </h3>
        {monthly && (
          <>
            <AutoStats auto={monthly.auto} />
            <div className="muted" style={{ marginBottom: 14 }}>
              当前节点进度：已点亮 {monthly.node_state.lit_count} / {monthly.node_state.node_count} · 当前净值 {monthly.node_state.nav.toFixed(4)}
            </div>
            <div className="grid grid-2">
              <label className="field"><span>体系迭代 · 这个月对交易系统的思考与修正</span>
                <textarea value={monthly.system_iteration} onChange={e => setMonthly({ ...monthly, system_iteration: e.target.value })} placeholder="规则要不要改？哪条被证伪了？" />
              </label>
              <label className="field"><span>下月目标</span>
                <textarea value={monthly.next_goal} onChange={e => setMonthly({ ...monthly, next_goal: e.target.value })} placeholder="下个月的目标：不止是收益，还有行为目标" />
              </label>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
