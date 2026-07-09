import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../components';
import { AutoStats, isoWeek, type PeriodAuto } from './periodicShared';

interface WeeklyData {
  year: number;
  week: number;
  right_things: string;
  wrong_things: string;
  next_strategy: string;
  auto: PeriodAuto;
}

export default function WeeklyReview() {
  const toast = useToast();
  const now = new Date();
  const [defYear, defWeek] = isoWeek(now);
  const [wk, setWk] = useState({ year: defYear, week: defWeek });
  const [weekly, setWeekly] = useState<WeeklyData | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [saving, setSaving] = useState(false);

  const loadWeekly = useCallback(() => {
    api.get<WeeklyData>(`/api/reviews/weekly/${wk.year}/${wk.week}`).then(setWeekly).catch(e => toast(String(e)));
  }, [wk, toast]);

  useEffect(loadWeekly, [loadWeekly]);

  const shiftWeek = (delta: number) => {
    const monday = new Date(Date.UTC(wk.year, 0, 4));
    monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() || 7) + 1 + (wk.week - 1 + delta) * 7);
    const [y, w] = isoWeek(new Date(monday.getUTCFullYear(), monday.getUTCMonth(), monday.getUTCDate()));
    setWk({ year: y, week: w });
  };

  const save = async (silent = false) => {
    if (!weekly) return;
    setSaving(true);
    try {
      await api.put(`/api/reviews/weekly/${wk.year}/${wk.week}`, {
        right_things: weekly.right_things,
        wrong_things: weekly.wrong_things,
        next_strategy: weekly.next_strategy,
      });
      if (!silent) toast('周复盘已保存');
    } catch (e) { toast(String(e)); } finally { setSaving(false); }
  };

  const aiReview = async () => {
    await save(true);
    setReviewing(true);
    try {
      const result = await api.post<Partial<WeeklyData>>(`/api/reviews/weekly/${wk.year}/${wk.week}/ai-review`);
      setWeekly(prev => prev ? {
        ...prev,
        right_things: result.right_things ?? prev.right_things,
        wrong_things: result.wrong_things ?? prev.wrong_things,
        next_strategy: result.next_strategy ?? prev.next_strategy,
      } : prev);
      toast('AI 周复盘草稿已生成，请核对后保存');
    } catch (e) { toast(String(e)); } finally { setReviewing(false); }
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">周复盘</h2>
          <div className="page-sub">拉远镜头，检视一周节奏与纪律</div>
        </div>
        <div className="row no-print">
          <button onClick={() => window.print()}>导出 PDF</button>
          <button onClick={aiReview} disabled={reviewing}>{reviewing ? 'AI 复盘中…' : '✦ AI 复盘'}</button>
          <button className="primary" onClick={() => save()} disabled={saving}>{saving ? '保存中…' : '保存'}</button>
        </div>
      </div>

      <div className="print-only print-header">
        <h3>Trading MS 周复盘 · {wk.year} 第 {wk.week} 周</h3>
      </div>

      <div className="card">
        <h3 className="card-title">
          <span>
            {wk.year} 第 {wk.week} 周
            {weekly && <span className="muted">（{weekly.auto.start} ~ {weekly.auto.end}）</span>}
          </span>
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
          </>
        )}
      </div>
    </div>
  );
}
