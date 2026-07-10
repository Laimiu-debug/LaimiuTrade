import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

type AiBusyCtx = {
  busy: boolean;
  label: string;
  setBusy: (on: boolean, label?: string) => void;
};

const Ctx = createContext<AiBusyCtx>({
  busy: false,
  label: '',
  setBusy: () => {},
});

export function AiBusyProvider({ children }: { children: ReactNode }) {
  const [busy, setBusyState] = useState(false);
  const [label, setLabel] = useState('AI 处理中…');
  const value = useMemo<AiBusyCtx>(() => ({
    busy,
    label,
    setBusy: (on, text) => {
      setBusyState(on);
      if (text) setLabel(text);
      else if (!on) setLabel('AI 处理中…');
    },
  }), [busy, label]);
  return (
    <Ctx.Provider value={value}>
      {children}
      {busy && (
        <div className="ai-busy-overlay no-print" role="status" aria-live="polite">
          <div className="ai-busy-card">
            <div className="quit-spinner" />
            <div className="ai-busy-text">{label}</div>
            <div className="ai-busy-sub">请稍候，不要关闭窗口</div>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

export function useAiBusy() {
  return useContext(Ctx);
}
