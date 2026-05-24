@echo off
chcp 65001 > nul
echo ========================================
echo  音乐下载器 Web版 启动中...
echo ========================================
echo.

cd /d %~dp0backend

echo 检查 Python 环境...
python --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo 安装依赖...
pip install -r requirements.txt

if errorlevel 1 (
    echo 错误: 依赖安装失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo  启动服务...
echo  访问 http://localhost:8000
echo  按 Ctrl+C 停止服务
echo ========================================
echo.

python main.py

pause
