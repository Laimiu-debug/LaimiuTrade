import { useCallback, useEffect, useRef, useState } from 'react';
import { api, fmtMoney, today } from '../api';
import { Empty, useToast, DateInput, NumberInput, Select } from '../components';

const FLOW_KIND_OPTIONS = [
  { value: 'initial', label: '初始资金' },
  { value: 'deposit', label: '入金' },
  { value: 'withdraw', label: '出金' },
];

interface FlowRow { id: number; flow_date: string; kind: string; amount: number; note: string }
interface SnapRow { id: number; snap_date: string; total_assets: number; note: string }
interface AccountImportPreview {
  snap_date: string;
  total_assets: number | null;
  available_cash: number | null;
  position_value?: number | null;
  positions: { code?: string; name?: string; qty?: number; price?: number; market_value?: number }[];
}

const KIND_LABEL: Record<string, string> = { initial: '初始资金', deposit: '入金', withdraw: '出金' };

export default function Capital() {
  const toast = useToast();
  const [flows, setFlows] = useState<FlowRow[]>([]);
  const [snaps, setSnaps] = useState<SnapRow[]>([]);
  const [estimating, setEstimating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [importPreview, setImportPreview] = useState<AccountImportPreview | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [flowForm, setFlowForm] = useState({ flow_date: today(), kind: 'deposit', amount: '', note: '' });
  const [snapForm, setSnapForm] = useState({ snap_date: today(), total_assets: '', note: '' });

  const reload = useCallback(() => {
    api.get<FlowRow[]>('/api/capital/flows').then(setFlows).catch(() => {});
    api.get<SnapRow[]>('/api/capital/snapshots').then(setSnaps).catch(() => {});
  }, []);

  useEffect(reload, [reload]);

  const addFlow = async () => {
    const amount = parseFloat(flowForm.amount);
    if (!amount || amount <= 0) { toast('请输入有效金额'); return; }
    try {
      await api.post('/api/capital/flows', { ...flowForm, amount });
      setFlowForm({ ...flowForm, amount: '', note: '' });
      toast('已记录');
      reload();
    } catch (e) { toast(String(e)); }
  };

  const addSnap = async () => {
    const assets = parseFloat(snapForm.total_assets);
    if (Number.isNaN(assets) || assets < 0) { toast('请输入有效总资产'); return; }
    try {
      await api.post('/api/capital/snapshots', { snap_date: snapForm.snap_date, total_assets: assets, note: snapForm.note });
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

  const hasInitial = flows.some(f => f.kind === 'initial');

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">资金账本</h2>
          <div className="page-sub">入出金按单位净值法折算份额，收益率不受出入金影响</div>
        </div>
      </div>

      {!hasInitial && (
        <div className="alert" style={{ marginBottom: 18 }}>
          尚未录入初始资金。请先添加一笔「初始资金」流水；之后可上传持仓截图识别总资产，或根据交易流水自动推算。
        </div>
      )}

      <div className="grid grid-2">
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
                  <span className="muted mono">持仓市值 ¥{fmtMoney(importPreview.position_value)}</span>
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
            <table>
              <thead><tr><th>日期</th><th style={{ textAlign: 'right' }}>总资产</th><th /></tr></thead>
              <tbody>
                {snaps.slice(0, 12).map(s => (
                  <tr key={s.id}>
                    <td>{s.snap_date}</td>
                    <td style={{ textAlign: 'right' }} className="mono">¥{fmtMoney(s.total_assets)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="danger-ghost" onClick={async () => {
                        await api.del(`/api/capital/snapshots/${s.id}`); reload();
                      }}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="card">
          <h3 className="card-title">出入金流水</h3>
          <div className="row" style={{ marginBottom: 16 }}>
            <DateInput value={flowForm.flow_date} onChange={v => setFlowForm({ ...flowForm, flow_date: v })} style={{ width: 150 }} />
            <Select
              value={flowForm.kind}
              onChange={v => setFlowForm({ ...flowForm, kind: v })}
              options={FLOW_KIND_OPTIONS}
              style={{ width: 118 }}
            />
            <NumberInput placeholder="金额" style={{ flex: 1, minWidth: 100 }}
              value={flowForm.amount}
              onChange={v => setFlowForm({ ...flowForm, amount: v })} />
            <button className="primary" onClick={addFlow}>记录</button>
          </div>
          {flows.length === 0 ? <Empty text="暂无流水" /> : (
            <table>
              <thead><tr><th>日期</th><th>类型</th><th style={{ textAlign: 'right' }}>金额</th><th /></tr></thead>
              <tbody>
                {flows.map(f => (
                  <tr key={f.id}>
                    <td>{f.flow_date}</td>
                    <td><span className={`tag${f.kind === 'withdraw' ? ' sell' : ' gold'}`}>{KIND_LABEL[f.kind] ?? f.kind}</span></td>
                    <td style={{ textAlign: 'right' }} className="mono">¥{fmtMoney(f.amount)}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="danger-ghost" onClick={async () => {
                        await api.del(`/api/capital/flows/${f.id}`); reload();
                      }}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
