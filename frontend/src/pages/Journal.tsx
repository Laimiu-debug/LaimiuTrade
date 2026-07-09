import { useCallback, useEffect, useRef, useState } from 'react';
import { api, fmtMoney, today, SCORE_DIMS, type DailyReview, type ScoreEntry, type WatchItem } from '../api';
import { Empty, SideTag, useToast } from '../components';

export default function Journal() {
  const toast = useToast();
  const [day, setDay] = useState(today());
  const [data, setData] = useState<DailyReview | null>(null);
  const [scoring, setScoring] = useState(false);
  const [saving, setSaving] = useState(false);
  const imgRef = useRef<HTMLInputElement>(null);

  const load = useCallback((d: string) => {
    api.get<DailyReview>(`/api/reviews/daily/${d}`).then(setData).catch(e => toast(String(e)));
  }, [toast]);

  useEffect(() => { load(day); }, [day, load]);

  const patch = (p: Partial<DailyReview>) => setData(d => (d ? { ...d, ...p } : d));

  const save = async (silent = false) => {
    if (!data) return;
    setSaving(true);
    try {
      await api.put(`/api/reviews/daily/${day}`, {
        market_observation: data.market_observation,
        decision_review: data.decision_review,
        mistakes: data.mistakes,
        scores: data.scores,
        next_market_forecast: data.next_market_forecast,
        next_watchlist: data.next_watchlist,
        next_position_plan: data.next_position_plan,
        next_risk_plan: data.next_risk_plan,
      });
      if (!silent) toast('复盘已保存');
    } catch (e) { toast(String(e)); } finally { setSaving(false); }
  };

  const aiScore = async () => {
    await save(true);
    setScoring(true);
    try {
      const result = await api.post<{ scores: Record<string, ScoreEntry>; summary: string }>(`/api/reviews/daily/${day}/ai-score`);
      patch({ scores: result.scores, ai_summary: result.summary });
      toast('AI 打分完成，可手动调整最终分');
    } catch (e) { toast(String(e)); } finally { setScoring(false); }
  };

  const setFinalScore = (dim: string, value: number) => {
    if (!data) return;
    const entry = { ...(data.scores[dim] ?? {}) };
    entry.final = entry.final === value ? null : value;
    patch({ scores: { ...data.scores, [dim]: entry } });
  };

  const uploadImage = async (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    try {
      await api.post(`/api/reviews/daily/${day}/images`, fd);
      load(day);
    } catch (e) { toast(String(e)); }
    if (imgRef.current) imgRef.current.value = '';
  };

  const watchlist = data?.next_watchlist ?? [];
  const setWatch = (i: number, p: Partial<WatchItem>) => {
    const next = watchlist.map((w, idx) => (idx === i ? { ...w, ...p } : w));
    patch({ next_watchlist: next });
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">每日复盘</h2>
          <div className="page-sub">复盘是交易者的第二战场</div>
        </div>
        <div className="row no-print">
          <input type="date" style={{ width: 150 }} value={day} onChange={e => setDay(e.target.value)} />
          <button onClick={() => window.print()}>导出 PDF</button>
          <button className="primary" onClick={() => save()} disabled={saving}>{saving ? '保存中…' : '保存'}</button>
        </div>
      </div>

      <div className="print-only" style={{ marginBottom: 16 }}>
        <h3 style={{ margin: 0 }}>Trading MS 每日复盘 · {day}</h3>
      </div>

      {data && (
        <>
          <div className="grid grid-2">
            <div className="card">
              <h3 className="card-title">当日交易（自动带出）</h3>
              {data.trades.length === 0 ? <Empty text="当日无交易记录" /> : (
                <table>
                  <thead><tr><th>标的</th><th>方向</th><th style={{ textAlign: 'right' }}>价格</th><th style={{ textAlign: 'right' }}>数量</th><th style={{ textAlign: 'right' }}>费用</th></tr></thead>
                  <tbody>
                    {data.trades.map(t => (
                      <tr key={t.id}>
                        <td>{t.name} <span className="muted mono">{t.code}</span></td>
                        <td><SideTag side={t.side} /></td>
                        <td style={{ textAlign: 'right' }} className="mono">{t.price}</td>
                        <td style={{ textAlign: 'right' }} className="mono">{t.qty}</td>
                        <td style={{ textAlign: 'right' }} className="mono muted">{t.fees}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="muted" style={{ marginTop: 10 }}>
                收盘总资产：{data.snapshot != null ? `¥${fmtMoney(data.snapshot)}` : '未录入（到资金账本补录）'}
              </div>
            </div>

            <div className="card">
              <h3 className="card-title">
                操作打分
                <button className="ghost no-print" onClick={aiScore} disabled={scoring}>
                  {scoring ? 'AI 分析中…' : '✦ AI 打分'}
                </button>
              </h3>
              {Object.entries(SCORE_DIMS).map(([dim, label]) => {
                const entry = data.scores[dim] ?? {};
                return (
                  <div className="score-row" key={dim}>
                    <span className="score-dim">{label}</span>
                    <div className="score-dots">
                      {Array.from({ length: 10 }, (_, i) => i + 1).map(v => (
                        <button key={v} className={`score-dot${(entry.final ?? 0) >= v ? ' on' : ''}`}
                          title={`${v}分`} onClick={() => setFinalScore(dim, v)} />
                      ))}
                    </div>
                    <span className="score-comment" title={entry.comment}>
                      {entry.ai != null && <span className="tag gold">AI {entry.ai}</span>} {entry.comment ?? ''}
                    </span>
                  </div>
                );
              })}
              {data.ai_summary && <div className="muted" style={{ marginTop: 12, lineHeight: 1.7 }}>「{data.ai_summary}」</div>}
            </div>
          </div>

          <div className="card" style={{ marginTop: 18 }}>
            <h3 className="card-title">复盘正文</h3>
            <label className="field"><span>盘面观察 · 大盘 / 板块 / 市场情绪</span>
              <textarea value={data.market_observation} onChange={e => patch({ market_observation: e.target.value })} placeholder="今天市场发生了什么？" />
            </label>
            <label className="field"><span>决策复盘 · 每笔操作的理由与对错</span>
              <textarea value={data.decision_review} onChange={e => patch({ decision_review: e.target.value })} placeholder="为什么买？为什么卖？现在看对了还是错了？" />
            </label>
            <label className="field"><span>错误与教训</span>
              <textarea value={data.mistakes} onChange={e => patch({ mistakes: e.target.value })} placeholder="今天犯了什么错？下次如何避免？" />
            </label>

            <div className="row no-print">
              <input ref={imgRef} type="file" accept="image/*" style={{ display: 'none' }}
                onChange={e => e.target.files?.[0] && uploadImage(e.target.files[0])} />
              <button onClick={() => imgRef.current?.click()}>+ 粘贴K线截图</button>
            </div>
            {data.images.length > 0 && (
              <div className="row" style={{ marginTop: 12 }}>
                {data.images.map(url => (
                  <div key={url} style={{ position: 'relative' }}>
                    <img className="img-thumb" src={url} onClick={() => window.open(url)} />
                    <button className="danger-ghost no-print" style={{ position: 'absolute', top: 2, right: 2 }}
                      onClick={async () => {
                        await api.del(`/api/reviews/daily/${day}/images?url=${encodeURIComponent(url)}`);
                        load(day);
                      }}>×</button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card" style={{ marginTop: 18 }}>
            <h3 className="card-title">次日预研</h3>
            <div className="grid grid-2">
              <label className="field"><span>大盘预判</span>
                <textarea value={data.next_market_forecast} onChange={e => patch({ next_market_forecast: e.target.value })} placeholder="明天大盘怎么走？多空条件是什么？" />
              </label>
              <label className="field"><span>仓位计划</span>
                <textarea value={data.next_position_plan} onChange={e => patch({ next_position_plan: e.target.value })} placeholder="明天计划保持几成仓？" />
              </label>
            </div>
            <label className="field"><span>风险预案</span>
              <textarea value={data.next_risk_plan} onChange={e => patch({ next_risk_plan: e.target.value })} placeholder="跌破哪里止损？突发利空怎么办？" />
            </label>

            <div className="card-title" style={{ marginTop: 8 }}>
              <span>关注标的</span>
              <button className="ghost no-print" onClick={() => patch({ next_watchlist: [...watchlist, { code: '', name: '', condition: '', action: '' }] })}>+ 添加</button>
            </div>
            {watchlist.length === 0 ? <Empty text="明天重点盯谁？触发什么条件做什么？" /> : watchlist.map((w, i) => (
              <div className="row" key={i} style={{ marginBottom: 8 }}>
                <input placeholder="代码" style={{ width: 90 }} value={w.code} onChange={e => setWatch(i, { code: e.target.value })} />
                <input placeholder="名称" style={{ width: 100 }} value={w.name} onChange={e => setWatch(i, { name: e.target.value })} />
                <input placeholder="触发条件（如：放量站上20日线）" style={{ flex: 2, minWidth: 140 }} value={w.condition} onChange={e => setWatch(i, { condition: e.target.value })} />
                <input placeholder="动作（如：3成仓介入）" style={{ flex: 1, minWidth: 100 }} value={w.action} onChange={e => setWatch(i, { action: e.target.value })} />
                <button className="danger-ghost no-print" onClick={() => patch({ next_watchlist: watchlist.filter((_, idx) => idx !== i) })}>×</button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
