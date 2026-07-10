import { useCallback, useEffect, useState } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { api } from '../api';
import { exportWeeklyPdf } from '../exportPdf';
import { useToast } from '../components';
import {
  AutoStats, PeriodicField, WeeklyPrintBody, isoWeek, type PeriodAuto,
} from './periodicShared';

interface WeeklyData {
  year: number;
  week: number;
  right_things: string;
  wrong_things: string;
  market_review: string;
  next_strategy: string;
  auto: PeriodAuto;
}

export default function WeeklyReview() {
  const toast = useToast();
  const now = new Date();
  const [defYear, defWeek] = isoWeek(now);
  const [wk, setWk] = useState({ year: defYear, week: defWeek });
  const [weekly, setWeekly] = useState<WeeklyData | null>(null);
  const [username, setUsername] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    api.get<{ pdf_username?: string }>('/api/settings').then(v => setUsername(v.pdf_username ?? '')).catch(() => {});
  }, []);

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
        market_review: weekly.market_review,
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
        market_review: result.market_review ?? prev.market_review,
        right_things: result.right_things ?? prev.right_things,
        wrong_things: result.wrong_things ?? prev.wrong_things,
        next_strategy: result.next_strategy ?? prev.next_strategy,
      } : prev);
      toast('AI 周复盘草稿已生成，请核对后保存');
    } catch (e) { toast(String(e)); } finally { setReviewing(false); }
  };

  const exportPdf = async () => {
    if (!weekly) return;
    await save(true);
    setExporting(true);
    try {
      const bodyHtml = renderToStaticMarkup(
        <WeeklyPrintBody
          username={username}
          year={wk.year}
          week={wk.week}
          periodLabel={periodLabel}
          auto={weekly.auto}
          market_review={weekly.market_review}
          right_things={weekly.right_things}
          wrong_things={weekly.wrong_things}
          next_strategy={weekly.next_strategy}
        />,
      );
      await exportWeeklyPdf(
        wk.year, wk.week, bodyHtml,
        msg => toast(msg),
        msg => toast(msg),
      );
    } finally { setExporting(false); }
  };

  const periodLabel = weekly ? `${weekly.auto.start} ~ ${weekly.auto.end}` : '';

  return (
    <div className="fade-in periodic-page">
      <div className="page-head no-print">
        <div>
          <h2 className="page-title">周复盘</h2>
          <div className="page-sub">拉远镜头，检视一周节奏与纪律</div>
        </div>
        <div className="row">
          <button onClick={exportPdf} disabled={exporting || !weekly}>{exporting ? '导出中…' : '导出 PDF'}</button>
          <button onClick={aiReview} disabled={reviewing}>{reviewing ? 'AI 复盘中…' : '✦ AI 复盘'}</button>
          <button className="primary" onClick={() => save()} disabled={saving}>{saving ? '保存中…' : '保存'}</button>
        </div>
      </div>

      <div className="periodic-shell">
        <div className="periodic-toolbar no-print">
          <h3 className="periodic-period-title">
            {wk.year} 第 {wk.week} 周
            {weekly && <span className="muted">（{periodLabel}）</span>}
          </h3>
          <span className="row">
            <button className="ghost" onClick={() => shiftWeek(-1)}>← 上一周</button>
            <button className="ghost" onClick={() => shiftWeek(1)}>下一周 →</button>
          </span>
        </div>

        {weekly && (
          <>
            <div className="no-print">
              <AutoStats auto={weekly.auto} />
            </div>
            <div className="periodic-grid periodic-grid-4 no-print">
              <PeriodicField label="本周盘面回顾" value={weekly.market_review}
                onChange={v => setWeekly({ ...weekly, market_review: v })}
                placeholder="资金去了哪些板块？整体热度如何？大盘向上还是向下？" />
              <PeriodicField label="本周做对的事" value={weekly.right_things}
                onChange={v => setWeekly({ ...weekly, right_things: v })}
                placeholder="坚持了什么原则？哪些操作值得复制？" />
              <PeriodicField label="本周做错的事" value={weekly.wrong_things}
                onChange={v => setWeekly({ ...weekly, wrong_things: v })}
                placeholder="违背了什么纪律？亏损的根源？" />
              <PeriodicField label="下周策略" value={weekly.next_strategy}
                onChange={v => setWeekly({ ...weekly, next_strategy: v })}
                placeholder="下周的仓位基调与主攻方向" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
