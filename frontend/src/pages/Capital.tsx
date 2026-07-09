import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmtMoney, today } from '../api';
import { Empty, useToast, DateInput, NumberInput } from '../components';

interface SnapPosition { code?: string; name?: string; qty?: number; price?: number; market_value?: number }
interface SnapRow {
  id: number;
  snap_date: string;
  total_assets: number;
  available_cash?: number | null;
  position_value?: number | null;
  positions: SnapPosition[];
  note: string;
}
interface AccountImportPreview {
  snap_date: string;
  total_assets: number | null;
  available_cash: number | null;
  position_value?: number | null;
  positions: SnapPosition[];
}

export default function Capital() {
  const toast = useToast();
  const [snaps, setSnaps] = useState<SnapRow[]>([]);
  const [hasInitial, setHasInitial] = useState(true);
  const [estimating, setEstimating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importPreview, setImportPreview] = useState<AccountImportPreview | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [snapForm, setSnapForm] = useState({ snap_date: today(), total_assets: '', note: '' });
  const [expandedSnapId, setExpandedSnapId] = useState<number | null>(null);

  const reload = useCallback(() => {
    api.get<SnapRow[]>('/api/capital/snapshots').then(setSnaps).catch(() => {});
    api.get<{ has_initial: boolean }>('/api/capital/status').then(r => setHasInitial(r.has_initial)).catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  const addSnap = async () => {
    const assets = parseFloat(snapForm.total_assets);
    if (Number.isNaN(assets) || assets < 0) { toast('请输入有效总资产'); return; }
    try {
      await api.post('/api/capital/snapshots', {
        snap_date: snapForm.snap_date,
        total_assets: assets,
        note: snapForm.note,
        positions: importPreview?.positions ?? [],
        available_cash: importPreview?.available_cash ?? null,
        position_value: importPreview?.position_value ?? null,
      });
      setSnapForm({ ...snapForm, total_assets: '', note: '' });
      setImportPreview(null);
      toast('快照已保存');
      reload();
    } catch (e) { toast(String(e)); }
  };

  const estimateFromTrades = async () => {
    setEstimating(true);
    try {
      const est = await api.get<{
        ok: boolean;
        message?: string;
        snap_date?: string;
        total_assets?: number;
        cash?: number;
        position_value?: number;
        positions?: SnapPosition[];
        reason?: string;
      }>(`/api/capital/estimate?date=${snapForm.snap_date}`);
      if (!est.ok) {
        toast(est.message ?? '无法推算，请先录入初始资金');
        return;
      }
      setSnapForm({
        ...snapForm,
        snap_date: est.snap_date ?? snapForm.snap_date,
        total_assets: String(est.total_assets ?? ''),
        note: est.message ?? '',
      });
      setImportPreview({
        snap_date: est.snap_date ?? snapForm.snap_date,
        total_assets: est.total_assets ?? null,
        available_cash: est.cash ?? null,
        position_value: est.position_value ?? null,
        positions: est.positions ?? [],
      });
      toast(`已填入推算值：现金 ¥${fmtMoney(est.cash ?? 0)} + 持仓 ¥${fmtMoney(est.position_value ?? 0)}`);
    } catch (e) { toast(String(e)); } finally {
      setEstimating(false);
    }
  };

  const uploadAccountScreenshot = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const result = await api.post<AccountImportPreview>('/api/capital/import/screenshot', fd);
      setImportPreview(result);
      const computedTotal = (result.position_value ?? 0) + (result.available_cash ?? 0);
      const totalHint = result.total_assets ?? (computedTotal > 0 ? computedTotal : null);
      setSnapForm({
        ...snapForm,
        snap_date: result.snap_date,
        total_assets: totalHint != null ? String(totalHint) : snapForm.total_assets,
        note: '持仓截图识别',
      });
      if (totalHint != null) {
        toast(`识别到总资产 ¥${fmtMoney(totalHint)}，请核对后保存`);
      } else if (result.positions.length > 0) {
        toast(`识别到 ${result.positions.length} 条持仓，请核对后保存或从交易推算`);
      } else {
        toast('未能识别有效数据，请手动填写');
      }
    } catch (e) { toast(String(e)); } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">资金账本</h2>
          <div className="page-sub">记录每日收盘快照与持仓；出入金请在「设置」中管理</div>
        </div>
      </div>

      {!hasInitial && (
        <div className="alert" style={{ marginBottom: 18 }}>
          尚未录入初始资金。请先到 <Link to="/settings">设置 → 出入金流水</Link> 添加「初始资金」；之后可在此上传持仓截图或从交易推算总资产。
        </div>
      )}

      <div className="card">
        <div className="page-head" style={{ marginBottom: 12 }}>
          <h3 className="card-title" style={{ margin: 0 }}>每日收盘快照</h3>
          <div className="row">
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => e.target.files?.[0] && uploadAccountScreenshot(e.target.files[0])} />
            <button onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? '识别中…' : '上传持仓截图'}
            </button>
            <button onClick={estimateFromTrades} disabled={estimating || !hasInitial}>
              {estimating ? '推算中…' : '从交易推算'}
            </button>
          </div>
        </div>
        <div className="row" style={{ marginBottom: 16 }}>
          <DateInput value={snapForm.snap_date} onChange={v => setSnapForm({ ...snapForm, snap_date: v })} style={{ width: 150 }} />
          <NumberInput placeholder="收盘总资产（现金+持仓市值）" style={{ flex: 1, minWidth: 140 }}
            value={snapForm.total_assets}
            onChange={v => setSnapForm({ ...snapForm, total_assets: v })} />
          <button className="primary" onClick={addSnap}>保存</button>
        </div>
        {importPreview && (importPreview.positions.length > 0 || importPreview.total_assets != null) && (
          <div style={{ marginBottom: 16, padding: '10px 12px', background: 'var(--surface-2)', borderRadius: 'var(--radius-sm)' }}>
            <div className="row" style={{ marginBottom: 8, gap: 16, flexWrap: 'wrap' }}>
              {importPreview.total_assets != null && (
                <span className="mono">总资产 ¥{fmtMoney(importPreview.total_assets)}</span>
              )}
              {importPreview.available_cash != null && (
                <span className="muted mono">可用 ¥{fmtMoney(importPreview.available_cash)}</span>
              )}
              {importPreview.position_value != null && (
                <span className="muted mono">持仓 ¥{fmtMoney(importPreview.position_value)}</span>
              )}
            </div>
            {importPreview.positions.length > 0 && (
              <>
                <div className="muted" style={{ marginBottom: 8, fontSize: 12 }}>
                  截图识别持仓（{importPreview.positions.length} 条）
                </div>
                <div className="card-scroll">
                  <table>
                    <thead><tr><th>代码</th><th>名称</th><th style={{ textAlign: 'right' }}>数量</th><th style={{ textAlign: 'right' }}>现价/成本</th><th style={{ textAlign: 'right' }}>市值</th></tr></thead>
                    <tbody>
                      {importPreview.positions.map((p, i) => (
                        <tr key={i}>
                          <td className="mono">{p.code ?? '—'}</td>
                          <td>{p.name ?? '—'}</td>
                          <td style={{ textAlign: 'right' }} className="mono">{p.qty ?? '—'}</td>
                          <td style={{ textAlign: 'right' }} className="mono">{p.price != null ? p.price.toFixed(3) : '—'}</td>
                          <td style={{ textAlign: 'right' }} className="mono">{p.market_value != null ? `¥${fmtMoney(p.market_value)}` : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        )}
        {snaps.length === 0 ? <Empty text="收盘后上传持仓截图，或从交易推算总资产" /> : (
          <div className="snap-card-list">
            {snaps.slice(0, 20).map(s => {
              const expanded = expandedSnapId === s.id;
              const positions = s.positions ?? [];
              return (
                <div className="snap-card" key={s.id}>
                  <div className="snap-card-head">
                    <div>
                      <div className="snap-card-date">{s.snap_date}</div>
                      <div className="snap-card-total mono">¥{fmtMoney(s.total_assets)}</div>
                    </div>
                    <div className="snap-card-actions">
                      {positions.length > 0 && (
                        <button className="ghost" style={{ fontSize: 12 }}
                          onClick={() => setExpandedSnapId(expanded ? null : s.id)}>
                          {expanded ? '收起' : `${positions.length} 只持仓`}
                        </button>
                      )}
                      <button className="danger-ghost" onClick={async () => {
                        await api.del(`/api/capital/snapshots/${s.id}`); reload();
                      }}>删除</button>
                    </div>
                  </div>
                  <div className="snap-card-meta">
                    {s.available_cash != null && (
                      <span className="muted mono">现金 ¥{fmtMoney(s.available_cash)}</span>
                    )}
                    {s.position_value != null && (
                      <span className="muted mono">持仓 ¥{fmtMoney(s.position_value)}</span>
                    )}
                    {positions.length > 0 && s.position_value == null && (
                      <span className="muted">{positions.length} 只标的</span>
                    )}
                    {s.note && <span className="muted">{s.note}</span>}
                  </div>
                  {(expanded || positions.length <= 3) && positions.length > 0 && (
                    <div className="snap-card-positions">
                      {positions.map((p, i) => (
                        <div className="snap-pos-row" key={`${p.code ?? i}-${i}`}>
                          <span className="mono">{p.code ?? '—'}</span>
                          <span>{p.name ?? '—'}</span>
                          <span className="mono muted">{p.qty != null ? `${p.qty}股` : '—'}</span>
                          <span className="mono muted">
                            {p.market_value != null ? `¥${fmtMoney(p.market_value)}` : p.price != null ? p.price.toFixed(3) : '—'}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
