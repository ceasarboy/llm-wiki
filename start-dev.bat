@echo off
chcp 65001 >nul
echo ============================================
echo   LLM-Wiki v3.0 开发模式启动
echo ============================================
echo.

:: 设置国内镜像环境变量
set HF_ENDPOINT=https://hf-mirror.com
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1

echo [1/2] 启动后端 (http://localhost:8000) ...
start "LLM-Wiki Backend" cmd /k "python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] 启动前端 (http://localhost:5173) ...
cd web
start "LLM-Wiki Frontend" cmd /k "npx vite"
cd ..

echo.
echo ============================================
echo   服务已启动！
echo   前端: http://localhost:5173
echo   后端: http://localhost:8000
echo   API文档: http://localhost:8000/docs
echo ============================================
echo.
echo 默认账号: admin / admin
echo.
echo 关闭此窗口不会停止服务，请关闭对应的命令行窗口来停止
echo.
pause
