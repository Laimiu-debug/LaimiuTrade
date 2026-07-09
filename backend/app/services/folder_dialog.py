"""本地文件夹选择（Windows 原生对话框）。"""

import subprocess
import sys


def pick_folder(title: str = "选择数据存储目录") -> str | None:
    """弹出系统文件夹选择框，返回绝对路径；取消则 None。"""
    if sys.platform != "win32":
        return None
    safe_title = title.replace("'", "''")
    ps = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '{safe_title}'
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
    Write-Output $dialog.SelectedPath
}}
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    path = (result.stdout or "").strip()
    return path if path else None
