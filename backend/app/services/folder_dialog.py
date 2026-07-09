"""本地文件夹选择（Windows）。

API 工作线程中不可直接调 GUI；通过独立 PowerShell 进程弹出对话框。
"""

import base64
import ctypes
import ctypes.wintypes as wintypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _powershell_encoded(script: str) -> list[str]:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return ["powershell.exe", "-NoProfile", "-STA", "-EncodedCommand", encoded]


def _pick_folder_powershell(title: str) -> tuple[str | None, str | None]:
    """PowerShell FolderBrowserDialog。返回 (path, error)，双 None 表示用户取消。"""
    safe_title = title.replace("'", "''")
    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{safe_title}'
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    Write-Output $dialog.SelectedPath
}}
"""
    try:
        result = subprocess.run(
            _powershell_encoded(ps),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, str(exc)
    if result.returncode != 0:
        err = (result.stderr or "").strip() or f"PowerShell 退出码 {result.returncode}"
        return None, err
    path = (result.stdout or "").strip()
    if not path:
        return None, None
    return path, None


def _pick_folder_win32(title: str) -> str | None:
    """SHBrowseForFolderW（仅用于独立子进程 CLI）。"""
    ole32 = ctypes.OleDLL("ole32")
    shell32 = ctypes.windll.shell32

    ole32.CoInitialize(None)
    try:
        BIF_RETURNONLYFSDIRS = 0x00000001
        BIF_NEWDIALOGSTYLE = 0x00000040

        class BROWSEINFOW(ctypes.Structure):
            _fields_ = [
                ("hwndOwner", wintypes.HWND),
                ("pidlRoot", ctypes.c_void_p),
                ("pszDisplayName", wintypes.LPWSTR),
                ("lpszTitle", wintypes.LPCWSTR),
                ("ulFlags", wintypes.UINT),
                ("lpfn", ctypes.c_void_p),
                ("lParam", ctypes.c_ssize_t),
                ("iImage", ctypes.c_int),
            ]

        display_name = ctypes.create_unicode_buffer(260)
        bi = BROWSEINFOW()
        bi.hwndOwner = 0
        bi.pidlRoot = 0
        bi.pszDisplayName = ctypes.cast(display_name, wintypes.LPWSTR)
        bi.lpszTitle = title
        bi.ulFlags = BIF_RETURNONLYFSDIRS | BIF_NEWDIALOGSTYLE
        bi.lpfn = 0
        bi.lParam = 0
        bi.iImage = 0

        pidl = shell32.SHBrowseForFolderW(ctypes.byref(bi))
        if not pidl:
            return None

        path_buf = ctypes.create_unicode_buffer(1024)
        try:
            if not shell32.SHGetPathFromIDListW(pidl, path_buf):
                return None
            return path_buf.value.strip() or None
        finally:
            ole32.CoTaskMemFree(pidl)
    finally:
        ole32.CoUninitialize()


def pick_folder_dialog(title: str = "选择数据存储目录") -> str | None:
    """在当前进程主线程弹出（供 CLI / 轻量子进程使用）。"""
    if sys.platform != "win32":
        return None
    path, err = _pick_folder_powershell(title)
    if path:
        return path
    if err:
        try:
            return _pick_folder_win32(title)
        except Exception:  # noqa: BLE001
            return None
    return None


def _helper_cmd(title: str, out_file: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "app.services.folder_dialog",
        title,
        out_file,
    ]


def _pick_folder_subprocess(title: str) -> tuple[str | None, str | None]:
    """开发模式兜底：轻量 Python 子进程。"""
    backend_dir = Path(__file__).resolve().parents[2]
    fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="tms-pick-")
    os.close(fd)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir)
    try:
        result = subprocess.run(
            _helper_cmd(title, out_path),
            timeout=120,
            cwd=str(backend_dir),
            env=env,
        )
        if result.returncode != 0:
            return None, f"子进程退出码 {result.returncode}"
        text = Path(out_path).read_text(encoding="utf-8").strip()
        return (text if text else None), None
    except (subprocess.TimeoutExpired, OSError) as exc:
        return None, str(exc)
    finally:
        Path(out_path).unlink(missing_ok=True)


def pick_folder(title: str = "选择数据存储目录") -> tuple[str | None, str | None]:
    """从 API 线程安全调用。返回 (path, error)，双 None 表示用户取消。"""
    if sys.platform != "win32":
        return None, "仅支持 Windows"

    path, err = _pick_folder_powershell(title)
    if path or err:
        return path, err

    if not getattr(sys, "frozen", False):
        return _pick_folder_subprocess(title)

    return None, "无法打开文件夹选择框，请手动粘贴路径"


def run_pick_folder_cli() -> None:
    """CLI：弹出对话框并将结果写入 out_file。"""
    if len(sys.argv) >= 2 and sys.argv[1] == "--pick-folder":
        title = sys.argv[2] if len(sys.argv) > 2 else "选择数据存储目录"
        out_file = sys.argv[3] if len(sys.argv) > 3 else ""
    else:
        title = sys.argv[1] if len(sys.argv) > 1 else "选择数据存储目录"
        out_file = sys.argv[2] if len(sys.argv) > 2 else ""
    path = pick_folder_dialog(title) or ""
    if out_file:
        Path(out_file).write_text(path, encoding="utf-8")
    else:
        print(path)


if __name__ == "__main__":
    run_pick_folder_cli()
