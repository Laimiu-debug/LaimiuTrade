"""exe 启动入口：起后端服务并自动打开浏览器。

无控制台窗口模式下 stdout/stderr 为 None，重定向到 data/app.log，
避免 uvicorn 日志写入失败导致进程崩溃。
"""

import socket
import sys
import threading
import webbrowser

import uvicorn

from app.database import DATA_DIR
from app.main import app

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def port_in_use() -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def main() -> None:
    if getattr(sys, "frozen", False) and sys.stdout is None:
        log_file = open(DATA_DIR / "app.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = log_file
        sys.stderr = log_file

    if port_in_use():
        # 已有实例在运行，直接打开页面即可
        webbrowser.open(URL)
        return

    threading.Timer(1.2, webbrowser.open, args=(URL,)).start()
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
