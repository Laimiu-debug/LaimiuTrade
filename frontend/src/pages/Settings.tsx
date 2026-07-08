import { useEffect, useState } from 'react';
import { api } from '../api';
import { useToast } from '../components';

type SettingsMap = Record<string, string> & { ai_api_key_set?: boolean };

export default function Settings() {
  const toast = useToast();
  const [values, setValues] = useState<SettingsMap>({});
  const [keySet, setKeySet] = useState(false);

  useEffect(() => {
    api.get<SettingsMap>('/api/settings').then(v => {
      setKeySet(Boolean(v.ai_api_key_set));
      delete v.ai_api_key_set;
      setValues(v);
    }).catch(() => {});
  }, []);

  const set = (k: string, v: string) => setValues(prev => ({ ...prev, [k]: v }));

  const save = async () => {
    try {
      await api.put('/api/settings', { values });
      toast('设置已保存');
      if (values.ai_api_key) setKeySet(true);
      set('ai_api_key', '');
    } catch (e) { toast(String(e)); }
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
        <h3 className="card-title">AI 配置（OpenAI 兼容接口）</h3>
        <div className="grid grid-2">
          <label className="field"><span>Base URL（如 https://dashscope.aliyuncs.com/compatible-mode/v1）</span>
            <input value={values.ai_base_url ?? ''} onChange={e => set('ai_base_url', e.target.value)} />
          </label>
          <label className="field"><span>API Key {keySet && <span className="tag gold">已配置</span>}</span>
            <input type="password" value={values.ai_api_key ?? ''} onChange={e => set('ai_api_key', e.target.value)}
              placeholder={keySet ? '留空则保持不变' : 'sk-…'} />
          </label>
          <label className="field"><span>文本模型（用于操作打分）</span>
            <input value={values.ai_text_model ?? ''} onChange={e => set('ai_text_model', e.target.value)} placeholder="如 qwen-plus / glm-4-air" />
          </label>
          <label className="field"><span>视觉模型（用于截图识别）</span>
            <input value={values.ai_vision_model ?? ''} onChange={e => set('ai_vision_model', e.target.value)} placeholder="如 qwen-vl-plus / glm-4v" />
          </label>
        </div>
        <div className="muted">未配置时核心功能不受影响：打分可手动填，交易可手动录。</div>
      </div>
    </div>
  );
}
