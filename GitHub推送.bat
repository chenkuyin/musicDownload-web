@echo off
chcp 65001 > nul
echo ========================================
echo  GitHub 推送脚本
echo ========================================
echo.

cd /d %~dp0

echo 请先在 GitHub 上创建仓库
echo.
echo 步骤:
echo 1. 访问 https://github.com/new
echo 2. 仓库名称输入: musicDownload-web
echo 3. 不要勾选 "Initialize this repository with a README"
echo 4. 点击 "Create repository"
echo 5. 复制仓库的 URL
echo.
echo.

set /p repo_url="请输入 GitHub 仓库 URL (例如: https://github.com/chenkuyin/musicDownload-web.git): "

echo.
echo 添加远程仓库并推送...
"C:\Program Files\Git\bin\git.exe" remote add origin %repo_url%
"C:\Program Files\Git\bin\git.exe" branch -M main
"C:\Program Files\Git\bin\git.exe" push -u origin main

echo.
if errorlevel 1 (
    echo 推送失败！请检查:
    echo 1. 仓库 URL 是否正确
    echo 2. 是否已配置 GitHub 访问权限
    echo.
    echo 可以使用以下命令配置 GitHub:
    echo   git config --global user.email "295340932@qq.com"
    echo   git config --global user.name "chenkuyin"
    echo.
    echo 使用 GitHub Personal Access Token:
    echo   git remote set-url origin https://YOUR_TOKEN@github.com/chenkuyin/musicDownload-web.git
) else (
    echo 推送成功！
    echo.
    echo 访问你的仓库: %repo_url%
)

pause
