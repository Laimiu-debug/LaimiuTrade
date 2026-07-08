import { createContext, useCallback, useContext, useState, type ReactNode } from 'react';

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
      {note !== undefined && <div className="stat-note">{note}</div>}
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
