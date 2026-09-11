@echo off
setlocal
cd /d "%~dp0"

rem ==== 按需修改：Python 路径（本项目依赖装在 D:\Python3.13）====
set "PY=D:\Python3.13\python.exe"
set "PYW=D:\Python3.13\pythonw.exe"
set "SCRIPT=%~dp0main.py"

rem ---- 1) 检查 Python ----
if not exist "%PY%" (
    echo [错误] 未找到 Python：%PY%
    echo 请右键编辑本脚本，把 PY / PYW 改成你实际的 Python 路径。
    pause
    exit /b 1
)

rem ---- 2) 已在运行则不重复启动（防止热键双触发）----
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe' or Name='python.exe'\" | Where-Object { $_.CommandLine -like '*main.py*' -and $_.CommandLine -like '*Voice_Vibe*' }; if ($p) { exit 0 } else { exit 1 }" >nul 2>nul
if not errorlevel 1 (
    echo Voice Vibe 已经在运行了（右下角托盘的麦克风图标）。
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

rem ---- 3) 依赖自检，缺失则自动安装 ----
"%PY%" -c "import PyQt6.QtCore, sounddevice, dashscope, keyboard, openai, pyperclip" >nul 2>nul
if errorlevel 1 (
    echo 首次使用：正在安装依赖（约 1-2 分钟，请稍候）…
    "%PY%" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    if errorlevel 1 goto :fail
)
goto :config

:fail
echo.
echo [错误] 依赖安装失败，请检查网络后重试。
pause
exit /b 1

rem ---- 4) 首次运行：生成配置并引导填写 API Key ----
:config
if exist config.toml goto :run
copy /y config.example.toml config.toml >nul
echo 首次使用：已生成 config.toml。
echo 请在即将打开的记事本中填入 asr.api_key（必填）和 llm.api_key（选填），
echo 保存关闭后，再次双击本脚本即可启动。
notepad config.toml
exit /b 0

rem ---- 5) 静默启动（无黑窗口）----
:run
if exist "%PYW%" (
    start "" "%PYW%" "%SCRIPT%"
) else (
    start "VoiceVibe" /min "%PY%" "%SCRIPT%"
)
echo Voice Vibe 已启动！
echo   按住 F2 说话，松开上屏（简单润色）
echo   按住 F3 深度润色 · 按住 F4 原始转写 · Esc 取消
echo   退出：右下角托盘麦克风图标右键 → 退出
ping -n 3 127.0.0.1 >nul
endlocal
