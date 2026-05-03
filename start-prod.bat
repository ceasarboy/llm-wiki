@echo off
chcp 65001 >nul
echo ============================================
echo   LLM-Wiki v3.0 生产模式启动
echo ============================================
echo.

:: 设置国内镜像环境变量
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

:: 检查前端是否已构建
if not exist "web\dist\index.html" (
    echo [警告] 前端未构建，正在构建...
    cd web
    call npx vite build
    cd ..
)

echo 启动后端 (http://localhost:8000) ...
echo 前端静态文件由后端直接提供
echo.
echo 默认账号: admin / admin
echo.
echo 按 Ctrl+C 停止服务
echo.

python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
