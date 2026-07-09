import { useCallback, useEffect, useRef, useState } from 'react';
import { api, fmtMoney, fmtPct, today, type RoundRow, type RoundStats, type TradeRow } from '../api';
import { Empty, SideTag, Stat, useToast, DateInput, NumberInput, StockPicker } from '../components';

interface PendingRow { id: number; trade_date: string; code: string; name: string; side: string; price: number; qty: number }

export default function Trades() {
  const toast = useToast();
  const [tab, setTab] = useState<'list' | 'rounds'>('list');
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [rounds, setRounds] = useState<{ rounds: RoundRow[]; stats: RoundStats } | null>(null);
  const [pending, setPending] = useState<PendingRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const [form, setForm] = useState({
    trade_date: today(), code: '', name: '', side: 'buy', price: '', qty: '', note: '',
  });

  const reload = useCallback(() => {
    api.get<TradeRow[]>('/api/trades').then(setTrades).catch(() => {});
    api.get<{ rounds: RoundRow[]; stats: RoundStats }>('/api/trades/rounds').then(setRounds).catch(() => {});
    api.get<PendingRow[]>('/api/trades/pending').then(setPending).catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  const addTrade = async () => {
    const price = parseFloat(form.price);
    const qty = parseInt(form.qty, 10);
    if (!form.code.trim() || !price || !qty) { toast('请填写代码、价格、数量'); return; }
    try {
      await api.post('/api/trades', { ...form, price, qty });
      setForm({ ...form, price: '', qty: '', note: '' });
      toast('交易已记录，费用已自动计算');
      reload();
    } catch (e) { toast(String(e)); }
  };

  const uploadScreenshot = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const result = await api.post<{ recognized: number; pending_created: number }>('/api/trades/import/screenshot', fd);
      toast(`识别出 ${result.recognized} 条，${result.pending_created} 条进入待确认`);
      reload();
    } catch (e) { toast(String(e)); } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const confirmPending = async (p: PendingRow) => {
    try {
      await api.post(`/api/trades/pending/${p.id}/confirm`, {
        trade_date: p.trade_date, code: p.code, name: p.name, side: p.side, price: p.price, qty: p.qty,
      });
      toast('已入库');
      reload();
    } catch (e) { toast(String(e)); }
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">交易记录</h2>
          <div className="page-sub">同一标的建仓到清仓自动归组为回合</div>
        </div>
        <div className="row">
          <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
            onChange={e => e.target.files?.[0] && uploadScreenshot(e.target.files[0])} />
          <button onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? '识别中…' : '上传截图识别'}
          </button>
        </div>
      </div>

      {pending.length > 0 && (
        <div className="card" style={{ marginBottom: 18, borderColor: 'rgba(212,175,106,0.4)' }}>
          <h3 className="card-title">待确认（截图识别结果，请核对后入库）</h3>
          <table>
            <thead><tr><th>日期</th><th>代码</th><th>名称</th><th>方向</th><th>价格</th><th>数量</th><th /></tr></thead>
            <tbody>
              {pending.map(p => (
                <tr key={p.id}>
                  <td>{p.trade_date}</td><td className="mono">{p.code}</td><td>{p.name}</td>
                  <td><SideTag side={p.side} /></td>
                  <td className="mono">{p.price}</td><td className="mono">{p.qty}</td>
                  <td style={{ textAlign: 'right' }}>
                    <button className="ghost" onClick={() => confirmPending(p)}>确认入库</button>
                    <button className="danger-ghost" onClick={async () => { await api.del(`/api/trades/pending/${p.id}`); reload(); }}>丢弃</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card" style={{ marginBottom: 18 }}>
        <h3 className="card-title">手动录入</h3>
        <div className="row">
          <DateInput value={form.trade_date} onChange={v => setForm({ ...form, trade_date: v })} style={{ width: 150 }} />
          <StockPicker
            code={form.code}
            name={form.name}
            onSelect={(code, name) => setForm({ ...form, code, name })}
            style={{ width: 200 }}
          />
          <select style={{ width: 80 }} value={form.side} onChange={e => setForm({ ...form, side: e.target.value })}>
            <option value="buy">买入</option>
            <option value="sell">卖出</option>
          </select>
          <NumberInput placeholder="价格" style={{ width: 90 }} value={form.price} onChange={v => setForm({ ...form, price: v })} />
          <NumberInput placeholder="数量(股)" style={{ width: 100 }} value={form.qty} onChange={v => setForm({ ...form, qty: v })} />
          <button className="primary" onClick={addTrade}>记录</button>
        </div>
      </div>

      <div className="row" style={{ marginBottom: 14 }}>
        <button className={tab === 'list' ? 'primary' : ''} onClick={() => setTab('list')}>流水</button>
        <button className={tab === 'rounds' ? 'primary' : ''} onClick={() => setTab('rounds')}>回合</button>
        {rounds && rounds.stats.total_rounds > 0 && (
          <span className="muted" style={{ marginLeft: 8 }}>
            已完成 {rounds.stats.total_rounds} 回合 · 胜率 {rounds.stats.win_rate ?? '—'}% · 盈亏比 {rounds.stats.profit_loss_ratio ?? '—'}
          </span>
        )}
      </div>

      {tab === 'list' && (
        <div className="card">
          {trades.length === 0 ? <Empty text="暂无交易记录" /> : (
            <table>
              <thead><tr><th>日期</th><th>标的</th><th>方向</th><th style={{ textAlign: 'right' }}>价格</th><th style={{ textAlign: 'right' }}>数量</th><th style={{ textAlign: 'right' }}>金额</th><th style={{ textAlign: 'right' }}>费用</th><th /></tr></thead>
              <tbody>
                {trades.map(t => (
                  <tr key={t.id}>
                    <td>{t.trade_date}</td>
                    <td>{t.name} <span className="muted mono">{t.code}</span>{t.source === 'import' && <span className="tag" style={{ marginLeft: 4 }}>导入</span>}</td>
                    <td><SideTag side={t.side} /></td>
                    <td style={{ textAlign: 'right' }} className="mono">{t.price.toFixed(3)}</td>
                    <td style={{ textAlign: 'right' }} className="mono">{t.qty}</td>
                    <td style={{ textAlign: 'right' }} className="mono">¥{fmtMoney(t.amount)}</td>
                    <td style={{ textAlign: 'right' }} className="mono muted">{t.fees.toFixed(2)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="danger-ghost" onClick={async () => { await api.del(`/api/trades/${t.id}`); reload(); }}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'rounds' && rounds && (
        <>
          {rounds.stats.total_rounds > 0 && (
            <div className="grid grid-4" style={{ marginBottom: 18 }}>
              <div className="card"><Stat small label="胜率" gold value={rounds.stats.win_rate != null ? `${rounds.stats.win_rate}%` : '—'} note={`${rounds.stats.win_count}胜 ${rounds.stats.lose_count}负`} /></div>
              <div className="card"><Stat small label="盈亏比" value={rounds.stats.profit_loss_ratio ?? '—'} note={`均盈 ${fmtMoney(rounds.stats.avg_win)} / 均亏 ${fmtMoney(rounds.stats.avg_loss)}`} /></div>
              <div className="card"><Stat small label="最长连胜 / 连亏" value={`${rounds.stats.max_win_streak} / ${rounds.stats.max_lose_streak}`} /></div>
              <div className="card"><Stat small label="累计回合盈亏" tone={rounds.stats.total_pnl >= 0 ? 'pos' : 'neg'} value={`¥${fmtMoney(rounds.stats.total_pnl)}`} /></div>
            </div>
          )}
          <div className="card">
            {rounds.rounds.length === 0 ? <Empty text="暂无回合" /> : (
              <table>
                <thead><tr><th>标的</th><th>周期</th><th>状态</th><th style={{ textAlign: 'right' }}>买入额</th><th style={{ textAlign: 'right' }}>盈亏</th><th style={{ textAlign: 'right' }}>收益率</th></tr></thead>
                <tbody>
                  {rounds.rounds.map((r, i) => (
                    <tr key={i}>
                      <td>{r.name} <span className="muted mono">{r.code}</span></td>
                      <td className="muted">{r.start_date} → {r.end_date ?? '持仓中'}</td>
                      <td>{r.status === 'closed' ? <span className="tag">已清仓</span> : r.status === 'open' ? <span className="tag gold">持仓 {r.position}股</span> : <span className="tag sell">异常</span>}</td>
                      <td style={{ textAlign: 'right' }} className="mono">¥{fmtMoney(r.buy_amount)}</td>
                      <td style={{ textAlign: 'right' }} className={`mono ${r.pnl != null ? (r.pnl >= 0 ? 'pos' : 'neg') : ''}`}>{r.pnl != null ? `¥${fmtMoney(r.pnl)}` : '—'}</td>
                      <td style={{ textAlign: 'right' }} className={`mono ${r.pnl_pct != null ? (r.pnl_pct >= 0 ? 'pos' : 'neg') : ''}`}>{fmtPct(r.pnl_pct)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}
