import { useEffect, useState } from 'react';
import { NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { api } from './api';
import Dashboard from './pages/Dashboard';
import Journal from './pages/Journal';
import WeeklyReview from './pages/WeeklyReview';
import MonthlyReview from './pages/MonthlyReview';
import Trades from './pages/Trades';
import Capital from './pages/Capital';
import Stats from './pages/Stats';
import Cards from './pages/Cards';
import Settings from './pages/Settings';

const THEME_KEY = 'lt-theme';
type Theme = 'dark' | 'light';

function applyTheme(t: Theme) {
  if (t === 'dark') document.documentElement.dataset.theme = 'dark';
  else delete document.documentElement.dataset.theme;
}

const NAV = [
  { to: '/', label: '总览', icon: 'M3 13h4v8H3zM10 8h4v13h-4zM17 3h4v18h-4z' },
  { to: '/journal', label: '每日复盘', icon: 'M4 4h16v16H4zM8 2v4M16 2v4M4 10h16' },
  { to: '/weekly', label: '周复盘', icon: 'M12 8v4l3 3M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0' },
  { to: '/monthly', label: '月复盘', icon: 'M4 4h16v16H4zM8 2v4M16 2v4M4 10h16M8 14h8M8 18h5' },
  { to: '/trades', label: '交易记录', icon: 'M3 17l6-6 4 4 8-8M17 7h4v4' },
  { to: '/capital', label: '资金账本', icon: 'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { to: '/stats', label: '统计分析', icon: 'M18 20V10M12 20V4M6 20v-6' },
  { to: '/cards', label: '灵感闪记', icon: 'M12 2l2.4 7.2H22l-6 4.6 2.3 7.2-6.3-4.5-6.3 4.5L8 13.8 2 9.2h7.6z' },
  { to: '/settings', label: '设置', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 1-.1 1.2l2 1.6-2 3.4-2.4-1a7 7 0 0 1-2 1.2L14 21h-4l-.4-2.6a7 7 0 0 1-2.1-1.2l-2.4 1-2-3.4 2-1.6A7 7 0 0 1 5 12c0-.4 0-.8.1-1.2l-2-1.6 2-3.4 2.4 1a7 7 0 0 1 2-1.2L10 3h4l.4 2.6a7 7 0 0 1 2.1 1.2l2.4-1 2 3.4-2 1.6c.1.4.1.8.1 1.2z' },
];

export default function App() {
  const location = useLocation();
  const [theme] = useState<Theme>(() => {
    const saved = localStorage.getItem(THEME_KEY);
    // 默认浅色（米色暖熊），仅显式选过 dark 才用深色
    return saved === 'dark' ? 'dark' : 'light';
  });
  const [navOpen, setNavOpen] = useState(false);
  const [quitState, setQuitState] = useState<'idle' | 'quitting' | 'quit'>('idle');

  useEffect(() => { applyTheme(theme); }, [theme]);
  useEffect(() => { setNavOpen(false); }, [location.pathname]);

  const toggleTheme = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
    // 图表颜色取自模块级常量，需重载页面才能刷新所有 echarts 实例
    setTimeout(() => window.location.reload(), 30);
  };

  const quitApp = async () => {
    if (!window.confirm('确定退出 Trading MS？退出后需重新双击 exe 启动。')) return;
    setQuitState('quitting');
    try {
      await api.post('/api/system/shutdown');
    } catch {
      // 进程已退出时 fetch 会失败，属正常情况
    }
    // 轮询探测后端是否已停：进程退出后任意请求都会快速失败
    const probe = async () => {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 1200);
        await fetch('/api/stats/overview', { signal: ctrl.signal });
        clearTimeout(t);
        return false; // 仍在响应
      } catch {
        return true; // 已停
      }
    };
    const startedAt = Date.now();
    const poll = async () => {
      // 最多探测 6 秒
      if (Date.now() - startedAt > 6000) { setQuitState('quit'); return; }
      if (await probe()) { setQuitState('quit'); return; }
      setTimeout(poll, 450);
    };
    setTimeout(poll, 500);
  };

  return (
    <div className={`app-shell${navOpen ? ' sidebar-open' : ''}`}>
      <button
        type="button"
        className="sidebar-backdrop no-print"
        aria-label="关闭导航"
        onClick={() => setNavOpen(false)}
      />
      <aside className="sidebar no-print">
        <div className="brand">
          <div className="brand-row">
            <img className="brand-logo" src="/logo.png" alt="logo" />
            <h1 className="brand-title">Trading MS</h1>
          </div>
          <div className="brand-sub">波段复利 · 长期主义</div>
        </div>
        {NAV.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          >
            <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d={item.icon} />
            </svg>
            {item.label}
          </NavLink>
        ))}
        <div className="nav-footer">
          <button type="button" className="nav-theme no-print" onClick={toggleTheme} title="切换深色/浅色主题">
            {theme === 'dark' ? '☀ 浅色' : '🌙 深色'}
          </button>
          <button type="button" className="nav-quit no-print" onClick={quitApp}>退出程序</button>
        </div>
      </aside>
      <main className="main">
        <div className="main-topbar no-print">
          <button type="button" className="nav-toggle" aria-label="打开导航" onClick={() => setNavOpen(true)}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 6h16M4 12h16M4 18h16" />
            </svg>
          </button>
          <span className="muted">Trading MS</span>
        </div>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/weekly" element={<WeeklyReview />} />
          <Route path="/monthly" element={<MonthlyReview />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/capital" element={<Capital />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/cards" element={<Cards />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>

      {quitState !== 'idle' && (
        <div className="quit-overlay">
          <div className="quit-card">
            {quitState === 'quitting' ? (
              <>
                <div className="quit-spinner" />
                <div className="quit-text">正在退出 Trading MS…</div>
                <div className="quit-sub">正在关闭本地服务</div>
              </>
            ) : (
              <>
                <div className="quit-text">程序已退出</div>
                <div className="quit-sub">本地服务已停止，现在可以关闭此浏览器标签页了。</div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
