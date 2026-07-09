import { useCallback, useEffect, useRef, useState } from 'react';
import {
  api, fmtMoney, today, SCORE_DIMS,
  type DailyReview, type ScoreEntry, type WatchItem,
} from '../api';
import { Empty, SideTag, useToast, DateInput, StockPicker } from '../components';

function ScoreDimRows({
  scores,
  onSetScore,
  side,
}: {
  scores: Record<string, ScoreEntry | undefined>;
  onSetScore?: (dim: string, value: number) => void;
  side?: string;
}) {
  return (
    <>
      {Object.entries(SCORE_DIMS).map(([dim, label]) => {
        const entry = scores[dim] ?? {};
        const dimLabel = dim === 'entry' && side === 'sell' ? '买点质量'
          : dim === 'exit' && side === 'buy' ? '卖点质量'
          : label;
        const inactive = (dim === 'entry' && side === 'sell') || (dim === 'exit' && side === 'buy');
        if (inactive && entry.ai == null && entry.final == null && !entry.comment) {
          return null;
        }
        return (
          <div className="score-row score-row-wrap" key={dim}>
            <span className="score-dim">{dimLabel}</span>
            <div className="score-dots">
              {Array.from({ length: 10 }, (_, i) => i + 1).map(v => (
                <button
                  key={v}
                  type="button"
                  className={`score-dot no-print${(entry.final ?? 0) >= v ? ' on' : ''}`}
                  title={`${v}分`}
                  disabled={!onSetScore}
                  onClick={() => onSetScore?.(dim, v)}
                />
              ))}
              <span className="print-only score-print-value">{entry.final ?? entry.ai ?? '—'}</span>
            </div>
            {entry.ai != null && <span className="tag gold no-print">AI {entry.ai}</span>}
            {entry.comment && <span className="score-comment-wrap">{entry.comment}</span>}
          </div>
        );
      })}
    </>
  );
}

export default function Journal() {
  const toast = useToast();
  const [day, setDay] = useState(today());
  const [data, setData] = useState<DailyReview | null>(null);
  const [scoringId, setScoringId] = useState<number | 'all' | null>(null);
  const [reviewing, setReviewing] = useState(false);
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
        trade_scores: data.trade_scores ?? {},
        next_market_forecast: data.next_market_forecast,
        next_watchlist: data.next_watchlist,
        next_position_plan: data.next_position_plan,
        next_risk_plan: data.next_risk_plan,
      });
      if (!silent) toast('复盘已保存');
    } catch (e) { toast(String(e)); } finally { setSaving(false); }
  };

  const applyScoreResult = (result: {
    trade_scores: Record<string, Record<string, ScoreEntry>>;
    scores: Record<string, ScoreEntry>;
    summary: string;
  }) => {
    patch({
      trade_scores: result.trade_scores,
      scores: result.scores,
      ai_summary: result.summary,
    });
  };

  const aiScoreAll = async () => {
    if (!data?.trades.length) { toast('当日无交易，无法打分'); return; }
    await save(true);
    setScoringId('all');
    try {
      const result = await api.post<{
        trade_scores: Record<string, Record<string, ScoreEntry>>;
        scores: Record<string, ScoreEntry>;
        summary: string;
      }>(`/api/reviews/daily/${day}/ai-score`);
      applyScoreResult(result);
      toast('全部交易 AI 分析完成');
    } catch (e) { toast(String(e)); } finally { setScoringId(null); }
  };

  const aiScoreOne = async (tradeId: number) => {
    await save(true);
    setScoringId(tradeId);
    try {
      const result = await api.post<{
        trade_scores: Record<string, Record<string, ScoreEntry>>;
        scores: Record<string, ScoreEntry>;
        summary: string;
      }>(`/api/reviews/daily/${day}/ai-score/${tradeId}`);
      applyScoreResult(result);
      toast('此笔交易 AI 分析完成');
    } catch (e) { toast(String(e)); } finally { setScoringId(null); }
  };

  const aiReview = async () => {
    await save(true);
    setReviewing(true);
    try {
      const result = await api.post<Partial<DailyReview>>(`/api/reviews/daily/${day}/ai-review`);
      patch({
        market_observation: result.market_observation ?? data?.market_observation ?? '',
        decision_review: result.decision_review ?? data?.decision_review ?? '',
        mistakes: result.mistakes ?? data?.mistakes ?? '',
        next_market_forecast: result.next_market_forecast ?? data?.next_market_forecast ?? '',
        next_position_plan: result.next_position_plan ?? data?.next_position_plan ?? '',
        next_risk_plan: result.next_risk_plan ?? data?.next_risk_plan ?? '',
      });
      toast('AI 复盘草稿已生成，请核对后保存');
    } catch (e) { toast(String(e)); } finally { setReviewing(false); }
  };

  const setTradeFinalScore = (tradeId: number, dim: string, value: number) => {
    if (!data) return;
    const key = String(tradeId);
    const tradeEntry = { ...(data.trade_scores?.[key] ?? {}) };
    const dimEntry = { ...(tradeEntry[dim] ?? {}) };
    dimEntry.final = dimEntry.final === value ? null : value;
    tradeEntry[dim] = dimEntry;
    patch({ trade_scores: { ...data.trade_scores, [key]: tradeEntry } });
  };

  const setDailyFinalScore = (dim: string, value: number) => {
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

  const tradeHasScores = (ts: Record<string, ScoreEntry | undefined>) =>
    Object.keys(SCORE_DIMS).some(dim => ts[dim]?.ai != null || ts[dim]?.final != null || ts[dim]?.comment);

  return (
    <div className="fade-in journal-page">
      <div className="page-head">
        <div>
          <h2 className="page-title">每日复盘</h2>
          <div className="page-sub">复盘是交易者的第二战场</div>
        </div>
        <div className="row no-print">
          <DateInput value={day} onChange={setDay} style={{ width: 150 }} />
          <button onClick={() => window.print()}>导出 PDF</button>
          <button onClick={aiReview} disabled={reviewing}>{reviewing ? 'AI 复盘中…' : '✦ AI 复盘'}</button>
          <button className="primary" onClick={() => save()} disabled={saving}>{saving ? '保存中…' : '保存'}</button>
        </div>
      </div>

      <div className="print-only print-header">
        <h3>Trading MS 每日复盘 · {day}</h3>
      </div>

      {data && (
        <>
          <div className="grid grid-2">
            <div className="card">
              <div className="page-head" style={{ marginBottom: 12 }}>
                <h3 className="card-title" style={{ margin: 0 }}>当日交易 · 逐条打分</h3>
                <button className="ghost no-print" onClick={aiScoreAll}
                  disabled={scoringId !== null || data.trades.length === 0}>
                  {scoringId === 'all' ? '分析中…' : '✦ AI 分析全部'}
                </button>
              </div>

              {data.trades.length === 0 ? <Empty text="当日无交易记录" /> : (
                <div className="trade-score-list">
                  {data.trades.map(t => {
                    const ts = data.trade_scores?.[String(t.id)] ?? {};
                    const hasScores = tradeHasScores(ts);
                    const tradeSummary = ts._summary?.comment;
                    return (
                      <div className="trade-score-card" key={t.id}>
                        <div className="trade-score-head">
                          <div className="trade-score-meta">
                            <SideTag side={t.side} />
                            <span className="trade-score-name">{t.name}</span>
                            <span className="muted mono">{t.code}</span>
                          </div>
                          <div className="row" style={{ gap: 8 }}>
                            <span className="trade-score-numbers mono muted">
                              {t.price} × {t.qty} · 费用 {t.fees}
                            </span>
                            <button className="ghost no-print" onClick={() => aiScoreOne(t.id)}
                              disabled={scoringId !== null}>
                              {scoringId === t.id ? '分析中…' : 'AI 分析此笔'}
                            </button>
                          </div>
                        </div>
                        {hasScores ? (
                          <div className="trade-score-body">
                            {tradeSummary && (
                              <div className="trade-score-summary">{tradeSummary}</div>
                            )}
                            <ScoreDimRows
                              scores={ts}
                              side={t.side}
                              onSetScore={(dim, v) => setTradeFinalScore(t.id, dim, v)}
                            />
                          </div>
                        ) : (
                          <div className="muted trade-score-empty">点击「AI 分析此笔」单独评价，或使用「AI 分析全部」</div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              <div className="muted journal-snapshot-note">
                收盘总资产：{data.snapshot != null ? `¥${fmtMoney(data.snapshot)}` : '未录入（到资金账本补录）'}
              </div>
            </div>

            <div className="card">
              <h3 className="card-title">整日操作概览</h3>
              <p className="muted" style={{ margin: '0 0 12px', fontSize: 12 }}>
                由各笔交易评分汇总，可手动调整
              </p>
              {Object.keys(SCORE_DIMS).some(dim => data.scores[dim]?.ai != null || data.scores[dim]?.comment) ? (
                <ScoreDimRows scores={data.scores} onSetScore={setDailyFinalScore} />
              ) : (
                <Empty text="完成逐条打分后，此处显示 6 维度汇总" />
              )}
              {data.ai_summary && (
                <div className="journal-day-summary">{data.ai_summary}</div>
              )}
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
                    <img className="img-thumb" src={url} alt="" onClick={() => window.open(url)} />
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
                <StockPicker
                  code={w.code}
                  name={w.name}
                  onSelect={(code, name) => setWatch(i, { code, name })}
                  style={{ flex: 2, minWidth: 180 }}
                />
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
