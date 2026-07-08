# LaimiuTrade · 波段复盘志

个人 A 股波段交易复盘日志。胜利目标：完成 50 个 30% 波段的复利增长。

## 功能

- **单位净值记账**：入出金按净值折算份额，收益率不受资金进出影响
- **50 个胜利节点**：净值 1.3ⁿ 阶梯，回撤即熄灭，记录每个节点的达成耗时
- **交易记录**：手动录入或上传同花顺截图 AI 识别；费用自动计算；建仓到清仓自动归组为回合，统计胜率/盈亏比
- **四层复盘**：每日复盘、次日预研、周复盘、月复盘，固定模板 + 自动数据
- **AI 操作打分**：6 维度（仓位/回撤/执行力/买点/卖点/情绪），结合当日行情，可手动修正
- **行情三源**：本地通达信直读 / akshare / 东方财富接口，可配置优先级
- **灵感闪记**：轻量卡片 + 每日随机温故
- **导出**：复盘打印为 PDF、JSON 全量备份、Markdown 导出

## 快速开始（exe 单文件）

已打包用户直接双击 `LaimiuTrade.exe` 即可：自动启动本地服务并打开浏览器，
数据保存在 exe 同目录的 `data/` 文件夹（迁移时连同 exe 一起拷走）。
若浏览器没有自动打开，手动访问 http://127.0.0.1:8000 。

### 自行打包 exe

```bash
cd frontend && npm run build && cd ..
backend\.venv\Scripts\pip install pyinstaller
backend\.venv\Scripts\pyinstaller --noconfirm --clean laimiutrade.spec
# 产物: dist\LaimiuTrade.exe
```

## 源码运行

环境要求：Python 3.10+、Node.js 18+

```bash
# 1. 构建前端（首次）
cd frontend
npm install
npm run build

# 2. 启动（回到项目根目录，双击 start.bat 或命令行）
start.bat
```

浏览器自动打开 http://127.0.0.1:8000 。

### 开发模式

```bash
# 后端
cd backend
.venv\Scripts\python -m uvicorn app.main:app --reload

# 前端（另开终端，带热更新，访问 http://localhost:5173）
cd frontend
npm run dev
```

## 数据

全部数据存于本地 `data/` 目录（SQLite 数据库 + 上传图片），不上传任何服务器。
换电脑时整个目录拷走即可。

## AI 配置（可选）

设置页填写 OpenAI 兼容接口的 Base URL、API Key、模型名（文本 + 视觉各一）。
不配置不影响核心记账与复盘功能。
