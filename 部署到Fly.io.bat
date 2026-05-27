@echo off
chcp 65001 > nul
echo ========================================
echo  Fly.io 部署脚本
echo ========================================
echo.

cd /d %~dp0

echo 检查 flyctl 是否安装...

flyctl --version > nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 flyctl
    echo.
    echo 请先安装 flyctl:
    echo.
    echo Windows PowerShell:
    echo   iwr https://fly.io/install.ps1 -useb ^| iex
    echo.
    echo 或使用安装脚本:
    echo   curl -L https://fly.io/install.sh ^| sh
    echo.
    echo 安装完成后，运行此脚本重试。
    pause
    exit /b 1
)

echo.
echo ========================================
echo  部署到 Fly.io
echo ========================================
echo.

echo 1. 登录 Fly.io (如果没有账号请先注册)
echo.
flyctl auth login

echo.
echo 2. 启动应用...
flyctl launch

echo.
echo 3. 部署应用...
flyctl deploy

echo.
echo ========================================
echo  部署完成！
echo ========================================
echo.

flyctl open

echo.
pause
