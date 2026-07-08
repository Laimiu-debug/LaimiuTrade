import { NavLink, Route, Routes } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import Journal from './pages/Journal';
import Periodic from './pages/Periodic';
import Trades from './pages/Trades';
import Capital from './pages/Capital';
import Stats from './pages/Stats';
import Cards from './pages/Cards';
import Settings from './pages/Settings';

const NAV = [
  { to: '/', label: '总览', icon: 'M3 13h4v8H3zM10 8h4v13h-4zM17 3h4v18h-4z' },
  { to: '/journal', label: '每日复盘', icon: 'M4 4h16v16H4zM8 2v4M16 2v4M4 10h16' },
  { to: '/periodic', label: '周·月复盘', icon: 'M12 8v4l3 3M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0' },
  { to: '/trades', label: '交易记录', icon: 'M3 17l6-6 4 4 8-8M17 7h4v4' },
  { to: '/capital', label: '资金账本', icon: 'M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' },
  { to: '/stats', label: '统计分析', icon: 'M18 20V10M12 20V4M6 20v-6' },
  { to: '/cards', label: '灵感闪记', icon: 'M12 2l2.4 7.2H22l-6 4.6 2.3 7.2-6.3-4.5-6.3 4.5L8 13.8 2 9.2h7.6z' },
  { to: '/settings', label: '设置', icon: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19 12a7 7 0 0 1-.1 1.2l2 1.6-2 3.4-2.4-1a7 7 0 0 1-2 1.2L14 21h-4l-.4-2.6a7 7 0 0 1-2.1-1.2l-2.4 1-2-3.4 2-1.6A7 7 0 0 1 5 12c0-.4 0-.8.1-1.2l-2-1.6 2-3.4 2.4 1a7 7 0 0 1 2-1.2L10 3h4l.4 2.6a7 7 0 0 1 2.1 1.2l2.4-1 2 3.4-2 1.6c.1.4.1.8.1 1.2z' },
];

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar no-print">
        <div className="brand">
          <h1 className="brand-title">LaimiuTrade</h1>
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
        <div className="nav-footer">数据存于本地 · v0.1</div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/periodic" element={<Periodic />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/capital" element={<Capital />} />
          <Route path="/stats" element={<Stats />} />
          <Route path="/cards" element={<Cards />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
