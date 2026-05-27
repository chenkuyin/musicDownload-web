@echo off
chcp 65001 > nul
echo ========================================
echo   音乐下载器 Web版 - 重启服务
echo ========================================
echo.

cd /d %~dp0backend

echo 查找占用端口8000的进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo 发现进程 PID: %%a
    echo 尝试停止进程...
    taskkill /F /PID %%a > nul 2>&1
)

echo.
echo 等待2秒...
timeout /t 2 /nobreak > nul

echo 启动服务...
echo ========================================
echo 访问 http://localhost:8000
echo 按 Ctrl+C 停止服务
echo ========================================
echo.

"C:\Users\chent\AppData\Local\Programs\Python\Python311\python.exe" main.py

pause
