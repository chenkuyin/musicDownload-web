@echo off
chcp 65001 > nul

echo 关闭占用端口8000的Python进程...

for /f "tokens=2" %%i in ('tasklist /FI "IMAGENAME eq python.exe" /FO TABLE /NH') do (
    for /f "tokens=1" %%j in ('wmic process where "ProcessId=%%i" get CommandLine /value ^| findstr main.py') do (
        echo 停止进程: %%i
        taskkill /F /PID %%i > nul 2>&1
    )
)

echo.
echo 等待2秒...
timeout /t 2 /nobreak > nul

echo 启动服务器...
cd c:\Users\chent\AI\musicDownload-web\backend
C:\Users\chent\AppData\Local\Programs\Python\Python311\python.exe main.py
