"""exe 启动入口：起后端服务 + 系统托盘图标 + 自动打开浏览器。

- 托盘图标右键菜单：打开界面 / 退出程序
- 无控制台窗口模式下 stdout/stderr 为 None，重定向到 data/app.log
"""

import os
import socket
import sys
import threading
import webbrowser
from pathlib import Path

import uvicorn
from PIL import Image

import pystray

from app.database import DATA_DIR
from app.main import app

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def assets_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "assets"
    return Path(__file__).resolve().parent / "assets"


def load_tray_image() -> Image.Image:
    """加载应用图标；打包后从 _MEIPASS/assets 读取。"""
    icon_path = assets_dir() / "icon.png"
    if icon_path.exists():
        img = Image.open(icon_path).convert("RGBA")
        return img.resize((64, 64), Image.Resampling.LANCZOS)
    # 兜底：简单占位图
    img = Image.new("RGBA", (64, 64), (12, 14, 19, 255))
    return img


def port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def run_server() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


def main() -> None:
    if getattr(sys, "frozen", False) and sys.stdout is None:
        log_file = open(DATA_DIR / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file

    if port_in_use():
        # 已有实例在运行，直接打开页面即可
        webbrowser.open(URL)
        return

    server = threading.Thread(target=run_server, daemon=True)
    server.start()
    threading.Timer(1.2, webbrowser.open, args=(URL,)).start()

    def on_open(icon, item):  # noqa: ARG001
        webbrowser.open(URL)

    def on_quit(icon, item):  # noqa: ARG001
        icon.visible = False
        icon.stop()
        os._exit(0)

    tray = pystray.Icon(
        "TradingMS",
        load_tray_image(),
        "Trading MS · 波段复盘志",
        pystray.Menu(
            pystray.MenuItem("打开界面", on_open, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出程序", on_quit),
        ),
    )
    tray.run()  # 阻塞在托盘消息循环，退出菜单触发 os._exit


if __name__ == "__main__":
    main()
