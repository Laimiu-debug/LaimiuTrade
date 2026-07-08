import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, fmtMoney, fmtPct, type FlashCard, type NodeInfo, type Overview } from '../api';
import { Chart, CHART_COLORS, baseAxis, baseTooltip } from '../Chart';
import { Empty, Stat } from '../components';

interface NodesResp {
  state: Overview['state'];
  nodes: NodeInfo[];
  timing: { level: number; first_lit: string; days_taken: number | null }[];
}

export default function Dashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [nodes, setNodes] = useState<NodesResp | null>(null);
  const [card, setCard] = useState<FlashCard | null>(null);

  useEffect(() => {
    api.get<Overview>('/api/stats/overview').then(setOverview).catch(() => {});
    api.get<NodesResp>('/api/capital/nodes').then(setNodes).catch(() => {});
    api.get<FlashCard | null>('/api/cards/random').then(setCard).catch(() => {});
  }, []);

  const state = overview?.state;
  const hasData = (overview?.curve.length ?? 0) > 0;

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">总览</h2>
          <div className="page-sub">{state?.day ? `数据截至 ${state.day}` : '尚未录入数据'}</div>
        </div>
        <Link className="btn" to="/journal">写今日复盘 →</Link>
      </div>

      {overview && overview.missing_reviews.length > 0 && (
        <div className="alert" style={{ marginBottom: 18 }}>
          有 {overview.missing_reviews.length} 个交易日未写复盘：
          {overview.missing_reviews.slice(-5).join('、')}
          {overview.missing_reviews.length > 5 ? ' …' : ''}
        </div>
      )}

      <div className="grid grid-4">
        <div className="card">
          <Stat label="当前净值" gold value={state ? state.nav.toFixed(4) : '—'}
            note={state && state.drawdown_pct < 0 ? <span className="neg">距峰值 {fmtPct(state.drawdown_pct)}</span> : '处于净值高点'} />
        </div>
        <div className="card">
          <Stat label="账户资产" value={state ? `¥${fmtMoney(state.assets)}` : '—'}
            note={state ? `份额 ${fmtMoney(state.shares)}` : ''} />
        </div>
        <div className="card">
          <Stat label="已点亮节点" gold value={state ? `${state.lit_count} / 50` : '—'}
            note={state?.next_level ? `下一节点 Lv.${state.next_level}` : '全部达成'} />
        </div>
        <div className="card">
          <Stat label="距下一节点" value={state?.next_gap_pct != null ? fmtPct(state.next_gap_pct, false) : '—'}
            note={state?.next_assets_target ? `目标资产 ¥${fmtMoney(state.next_assets_target)}` : ''} />
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card-title">五十节点征途<span className="muted">净值阶梯 ×1.3ⁿ · 回撤即熄灭</span></h3>
        {nodes ? (
          <div className="node-grid">
            {nodes.nodes.map(n => {
              const isNext = nodes.state.next_level === n.level;
              return (
                <div key={n.level}
                  className={`node-cell${n.lit ? ' lit' : ''}${isNext ? ' next' : ''}`}
                  title={`Lv.${n.level} 净值 ${n.threshold.toFixed(2)}${n.assets_equiv ? ` ≈ ¥${fmtMoney(n.assets_equiv)}` : ''}`}>
                  <span className="lv">{n.level}</span>
                </div>
              );
            })}
          </div>
        ) : <Empty text="录入初始资金后，征途从这里开始" />}
      </div>

      <div className="grid grid-2" style={{ marginTop: 18 }}>
        <div className="card">
          <h3 className="card-title">净值曲线</h3>
          {hasData ? (
            <Chart height={240} option={{
              grid: { left: 48, right: 16, top: 20, bottom: 28 },
              tooltip: baseTooltip,
              xAxis: { type: 'category', data: overview!.curve.map(p => p.date), ...baseAxis },
              yAxis: { type: 'value', scale: true, ...baseAxis },
              series: [{
                type: 'line', data: overview!.curve.map(p => p.nav),
                showSymbol: false, lineStyle: { color: CHART_COLORS.gold, width: 2 },
                areaStyle: { color: CHART_COLORS.goldSoft },
                markLine: state?.next_threshold ? {
                  silent: true, symbol: 'none',
                  lineStyle: { color: CHART_COLORS.text, type: 'dashed' },
                  data: [{ yAxis: state.next_threshold, label: { formatter: `Lv.${state.next_level}`, color: CHART_COLORS.text } }],
                } : undefined,
              }],
            }} />
          ) : <Empty text="暂无净值数据 — 先到「资金账本」录入初始资金与每日快照" />}
        </div>

        <div className="card">
          <h3 className="card-title">今日闪记<Link to="/cards" className="muted" style={{ textDecoration: 'none' }}>全部 →</Link></h3>
          {card ? (
            <div className="flash-card">
              <div className="content">{card.content}</div>
              <div className="meta">
                <span>{card.tags && card.tags.split(',').map(t => <span key={t} className="tag gold">{t}</span>)}</span>
                <span>{card.created_at.slice(0, 10)}</span>
              </div>
            </div>
          ) : <Empty text="还没有闪记。灵感来临时，记下来。" />}

          {overview && overview.round_stats.total_rounds > 0 && (
            <>
              <hr className="divider" />
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <Stat small label="回合胜率" value={overview.round_stats.win_rate != null ? `${overview.round_stats.win_rate}%` : '—'} />
                <Stat small label="盈亏比" value={overview.round_stats.profit_loss_ratio ?? '—'} />
                <Stat small label="累计回合盈亏"
                  tone={overview.round_stats.total_pnl >= 0 ? 'pos' : 'neg'}
                  value={`¥${fmtMoney(overview.round_stats.total_pnl)}`} />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
