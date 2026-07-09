import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../components';

type SettingsMap = Record<string, string> & { ai_score_api_key_set?: boolean; ai_ocr_api_key_set?: boolean };

export default function Settings() {
  const toast = useToast();
  const [values, setValues] = useState<SettingsMap>({});
  const [scoreKeySet, setScoreKeySet] = useState(false);
  const [ocrKeySet, setOcrKeySet] = useState(false);
  const [dataDir, setDataDir] = useState('');
  const [newDir, setNewDir] = useState('');
  const [moving, setMoving] = useState(false);
  const [testing, setTesting] = useState<'' | 'score' | 'ocr'>('');

  useEffect(() => {
    api.get<SettingsMap>('/api/settings').then(v => {
      setScoreKeySet(Boolean(v.ai_score_api_key_set));
      setOcrKeySet(Boolean(v.ai_ocr_api_key_set));
      setDataDir(v.data_dir ?? '');
      delete v.ai_score_api_key_set;
      delete v.ai_ocr_api_key_set;
      delete v.ai_api_key_set;
      delete v.data_dir;
      setValues(v);
    }).catch(() => {});
  }, []);

  const set = (k: string, v: string) => setValues(prev => ({ ...prev, [k]: v }));

  const save = async () => {
    try {
      await api.put('/api/settings', { values });
      toast('设置已保存');
      if (values.ai_score_api_key) setScoreKeySet(true);
      if (values.ai_ocr_api_key) setOcrKeySet(true);
      set('ai_score_api_key', '');
      set('ai_ocr_api_key', '');
    } catch (e) { toast(String(e)); }
  };

  const moveData = async () => {
    const target = newDir.trim();
    if (!target) { toast('请填写新的数据目录路径'); return; }
    if (!window.confirm(`将把数据迁移到「${target}」并需要重启程序生效，确认继续？`)) return;
    setMoving(true);
    try {
      await api.post('/api/system/move-data', { target_dir: target });
      toast('迁移完成，程序即将退出，请重新启动');
      setTimeout(() => window.location.reload(), 1800);
    } catch (e) { toast(String(e)); } finally { setMoving(false); }
  };

  const testAI = async (kind: 'score' | 'ocr') => {
    setTesting(kind);
    try {
      const payload = kind === 'ocr'
        ? { kind, base_url: values.ai_ocr_base_url ?? '', api_key: values.ai_ocr_api_key ?? '', model: values.ai_ocr_vision_model ?? '' }
        : { kind, base_url: values.ai_score_base_url ?? '', api_key: values.ai_score_api_key ?? '', model: values.ai_score_text_model ?? '' };
      const r = await api.post<{ ok: boolean; message: string }>('/api/settings/test-ai', payload);
      toast(r.message);
    } catch (e) { toast(String(e)); } finally { setTesting(''); }
  };

  return (
    <div className="fade-in">
      <div className="page-head">
        <div>
          <h2 className="page-title">设置</h2>
          <div className="page-sub">费率、行情源与 AI 配置</div>
        </div>
        <button className="primary" onClick={save}>保存全部设置</button>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <h3 className="card-title">胜利目标</h3>
        <div className="grid grid-2">
          <label className="field"><span>节点总数（默认 50）</span>
            <input type="number" min="1" value={values.node_count ?? ''} onChange={e => set('node_count', e.target.value)} />
          </label>
          <label className="field"><span>每节点涨幅 %（默认 30，即净值阶梯 ×1.3ⁿ）</span>
            <input type="number" min="1" value={values.wave_pct ?? ''} onChange={e => set('wave_pct', e.target.value)} />
          </label>
        </div>
        <div className="muted">修改后所有节点判定、进度条、耗时统计立即按新目标重算，历史数据不受影响。</div>
      </div>

      <div className="grid grid-2">
        <div className="card">
          <h3 className="card-title">交易费率</h3>
          <label className="field"><span>佣金费率（如 0.00025 = 万2.5）</span>
            <input value={values.commission_rate ?? ''} onChange={e => set('commission_rate', e.target.value)} />
          </label>
          <label className="field"><span>最低佣金（元）</span>
            <input value={values.commission_min ?? ''} onChange={e => set('commission_min', e.target.value)} />
          </label>
          <label className="field"><span>印花税率（卖出，如 0.0005 = 万5）</span>
            <input value={values.stamp_tax_rate ?? ''} onChange={e => set('stamp_tax_rate', e.target.value)} />
          </label>
          <label className="field"><span>过户费率（如 0.00001）</span>
            <input value={values.transfer_fee_rate ?? ''} onChange={e => set('transfer_fee_rate', e.target.value)} />
          </label>
        </div>

        <div className="card">
          <h3 className="card-title">行情数据源</h3>
          <label className="field"><span>优先级链路（逗号分隔：tdx / akshare / web）</span>
            <input value={values.market_priority ?? ''} onChange={e => set('market_priority', e.target.value)} />
          </label>
          <label className="field"><span>通达信 vipdoc 目录路径</span>
            <input value={values.tdx_path ?? ''} onChange={e => set('tdx_path', e.target.value)} placeholder="D:\new_tdx\vipdoc" />
          </label>
          <div className="muted">
            tdx：本地通达信日线直读，最快；akshare：免费公开接口；web：东方财富公开行情。逐源降级尝试。
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card-title">
          <span>AI 操作打分（文本模型）</span>
          <button className="ghost no-print" onClick={() => testAI('score')} disabled={testing !== ''}>
            {testing === 'score' ? '测试中…' : '测试连接'}
          </button>
        </h3>
        <div className="grid grid-3">
          <label className="field"><span>Base URL</span>
            <input value={values.ai_score_base_url ?? ''} onChange={e => set('ai_score_base_url', e.target.value)}
              placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </label>
          <label className="field"><span>API Key {scoreKeySet && <span className="tag gold">已配置</span>}</span>
            <input type="password" value={values.ai_score_api_key ?? ''} onChange={e => set('ai_score_api_key', e.target.value)}
              placeholder={scoreKeySet ? '留空则保持不变' : 'sk-…'} />
          </label>
          <label className="field"><span>文本模型</span>
            <input value={values.ai_score_text_model ?? ''} onChange={e => set('ai_score_text_model', e.target.value)} placeholder="如 qwen-plus / glm-4-air" />
          </label>
        </div>
        <div className="muted">仅在「每日复盘」的「AI 打分」使用。未配置时打分可手动填写。</div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card-title">
          <span>AI 截图识别（视觉模型）</span>
          <button className="ghost no-print" onClick={() => testAI('ocr')} disabled={testing !== ''}>
            {testing === 'ocr' ? '测试中…' : '测试连接'}
          </button>
        </h3>
        <div className="grid grid-3">
          <label className="field"><span>Base URL</span>
            <input value={values.ai_ocr_base_url ?? ''} onChange={e => set('ai_ocr_base_url', e.target.value)}
              placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1" />
          </label>
          <label className="field"><span>API Key {ocrKeySet && <span className="tag gold">已配置</span>}</span>
            <input type="password" value={values.ai_ocr_api_key ?? ''} onChange={e => set('ai_ocr_api_key', e.target.value)}
              placeholder={ocrKeySet ? '留空则保持不变' : 'sk-…'} />
          </label>
          <label className="field"><span>视觉模型</span>
            <input value={values.ai_ocr_vision_model ?? ''} onChange={e => set('ai_ocr_vision_model', e.target.value)} placeholder="如 qwen-vl-plus / glm-4v" />
          </label>
        </div>
        <div className="muted">仅在「上传截图识别」交易时使用，与打分互不影响。未配置时交易可手动录入。</div>
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 className="card-title">数据存储位置</h3>
        <div className="muted" style={{ marginBottom: 12 }}>
          当前：<span className="mono">{dataDir || '—'}</span>
        </div>
        <div className="row">
          <input placeholder="新的数据目录（绝对路径，如 D:\LaimiuData）" style={{ flex: 1, minWidth: 240 }}
            value={newDir} onChange={e => setNewDir(e.target.value)} />
          <button className="primary" onClick={moveData} disabled={moving}>
            {moving ? '迁移中…' : '迁移并重启'}
          </button>
        </div>
        <div className="muted" style={{ marginTop: 10 }}>
          把数据库、上传截图、日志迁移到新目录（需空目录），迁移后需重新启动程序生效。换电脑时拷走该目录即可。
        </div>
      </div>
    </div>
  );
}
