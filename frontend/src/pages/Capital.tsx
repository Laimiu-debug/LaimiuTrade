import { useCallback, useEffect, useState } from 'react';
import { api, fmtMoney, today } from '../api';
import { Empty, useToast } from '../components';

interface FlowRow { id: number; flow_date: string; kind: string; amount: number; note: string }
interface SnapRow { id: number; snap_date: string; total_assets: number; note: string }

const KIND_LABEL: Record<string, string> = { initial: '初始资金', deposit: '入金', withdraw: '出金' };

export default function Capital() {
  const toast = useToast();
  const [flows, setFlows] = useState<FlowRow[]>([]);
  const [snaps, setSnaps] = useState<SnapRow[]>([]);

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
      toast('快照已保存');
      reload();
    } catch (e) { toast(String(e)); }
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
          尚未录入初始资金。请先添加一笔「初始资金」流水，再录入当日总资产快照，净值系统即启动。
        </div>
      )}

      <div className="grid grid-2">
        <div className="card">
          <h3 className="card-title">每日收盘快照</h3>
          <div className="row" style={{ marginBottom: 16 }}>
            <input type="date" style={{ width: 150 }} value={snapForm.snap_date}
              onChange={e => setSnapForm({ ...snapForm, snap_date: e.target.value })} />
            <input type="number" placeholder="收盘总资产（现金+持仓市值）" style={{ flex: 1, minWidth: 140 }}
              value={snapForm.total_assets}
              onChange={e => setSnapForm({ ...snapForm, total_assets: e.target.value })} />
            <button className="primary" onClick={addSnap}>保存</button>
          </div>
          {snaps.length === 0 ? <Empty text="每个交易日收盘后，记一笔总资产" /> : (
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
            <input type="date" style={{ width: 150 }} value={flowForm.flow_date}
              onChange={e => setFlowForm({ ...flowForm, flow_date: e.target.value })} />
            <select style={{ width: 110 }} value={flowForm.kind}
              onChange={e => setFlowForm({ ...flowForm, kind: e.target.value })}>
              <option value="initial">初始资金</option>
              <option value="deposit">入金</option>
              <option value="withdraw">出金</option>
            </select>
            <input type="number" placeholder="金额" style={{ flex: 1, minWidth: 100 }}
              value={flowForm.amount}
              onChange={e => setFlowForm({ ...flowForm, amount: e.target.value })} />
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
