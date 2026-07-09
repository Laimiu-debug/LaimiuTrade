import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { api } from './api';

// ---------- Toast ----------

const ToastContext = createContext<(msg: string) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [msg, setMsg] = useState<string | null>(null);
  const show = useCallback((m: string) => {
    setMsg(m);
    window.setTimeout(() => setMsg(null), 2600);
  }, []);
  return (
    <ToastContext.Provider value={show}>
      {children}
      {msg && <div className="toast">{msg}</div>}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

// ---------- 小组件 ----------

export function Stat({ label, value, note, gold, small, tone }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  gold?: boolean;
  small?: boolean;
  tone?: 'pos' | 'neg' | null;
}) {
  const cls = ['stat-value', gold ? 'gold' : '', small ? 'sm' : '', tone ?? ''].join(' ');
  return (
    <div>
      <div className="stat-label">{label}</div>
      <div className={cls}>{value}</div>
      {note != null && note !== '' && <div className="stat-note">{note}</div>}
    </div>
  );
}

export function SideTag({ side }: { side: string }) {
  if (side === 'buy') return <span className="tag buy">买入</span>;
  if (side === 'sell') return <span className="tag sell">卖出</span>;
  return <span className="tag">{side}</span>;
}

export function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

// ---------- 日期 / 数字 / 股票选择 ----------

export function DateInput({ value, onChange, style, className }: {
  value: string;
  onChange: (v: string) => void;
  style?: CSSProperties;
  className?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const openPicker = () => {
    const el = ref.current;
    if (!el) return;
    if (typeof el.showPicker === 'function') el.showPicker();
    else el.focus();
  };
  return (
    <div className={`input-wrap date-input${className ? ` ${className}` : ''}`} style={style}>
      <input ref={ref} type="date" value={value} onChange={e => onChange(e.target.value)} />
      <button type="button" className="input-addon" onClick={openPicker} title="选择日期" aria-label="选择日期">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M4 4h16v16H4zM8 2v4M16 2v4M4 10h16" />
        </svg>
      </button>
    </div>
  );
}

export function NumberInput({ value, onChange, placeholder, style, className }: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  style?: CSSProperties;
  className?: string;
}) {
  return (
    <input
      type="text"
      inputMode="decimal"
      className={`input-number${className ? ` ${className}` : ''}`}
      style={style}
      value={value}
      placeholder={placeholder}
      onChange={e => {
        const v = e.target.value;
        if (v === '' || /^-?\d*\.?\d*$/.test(v)) onChange(v);
      }}
    />
  );
}

interface StockHit { code: string; name: string }

export function StockPicker({ code, name, onSelect, style }: {
  code: string;
  name: string;
  onSelect: (code: string, name: string) => void;
  style?: CSSProperties;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [hits, setHits] = useState<StockHit[]>([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);
  const editingRef = useRef(false);

  useEffect(() => {
    if (!editingRef.current) {
      setQuery(code && name ? `${code} ${name}` : code || name || '');
    }
  }, [code, name]);

  useEffect(() => {
    const q = query.trim();
    if (!open || q.length < 1) {
      setHits([]);
      return;
    }
    const t = window.setTimeout(() => {
      setLoading(true);
      api.get<StockHit[]>(`/api/market/search/stocks?q=${encodeURIComponent(q)}`)
        .then(setHits)
        .catch(() => setHits([]))
        .finally(() => setLoading(false));
    }, 220);
    return () => window.clearTimeout(t);
  }, [query, open]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const pick = (hit: StockHit) => {
    onSelect(hit.code, hit.name);
    setQuery(`${hit.code} ${hit.name}`);
    setOpen(false);
  };

  return (
    <div className="stock-picker" ref={wrapRef} style={style}>
      <input
        placeholder="输入代码或名称"
        value={query}
        onFocus={() => { editingRef.current = true; setOpen(true); }}
        onBlur={() => { editingRef.current = false; }}
        onChange={e => {
          setQuery(e.target.value);
          setOpen(true);
          if (!e.target.value.trim()) onSelect('', '');
        }}
      />
      {open && (loading || hits.length > 0 || query.trim().length >= 1) && (
        <div className="stock-picker-dropdown">
          {loading && <div className="stock-picker-item muted">搜索中…</div>}
          {!loading && hits.length === 0 && query.trim().length >= 1 && (
            <div className="stock-picker-item muted">无匹配结果</div>
          )}
          {!loading && hits.map(h => (
            <button key={h.code} type="button" className="stock-picker-item" onMouseDown={e => e.preventDefault()} onClick={() => pick(h)}>
              <span className="mono">{h.code}</span>
              <span>{h.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
