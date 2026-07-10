@echo off
setlocal
cd /d "%~dp0"

where cpolar >nul 2>nul
if errorlevel 1 (
  echo [ERROR] 未检测到 cpolar。
  echo 请先安装 cpolar 并登录账号，然后重新运行本脚本。
  echo 安装后确认命令行可以运行：cpolar version
  pause
  exit /b 1
)

start "光伏测算工具" powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_pv_tool.ps1"
echo 正在启动本地光伏测算工具，请稍等...
timeout /t 8 /nobreak >nul

echo.
echo 下面会生成一个公网链接。
echo 把 https 链接复制到微信，即可发给别人打开。
echo 注意：你的电脑和本窗口必须保持开启。
echo.
cpolar http 8501
