@echo off
chcp 65001 >nul
echo ============================================
echo   LLM-Wiki v3.0 一键安装脚本
echo ============================================
echo.

:: 检查 Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查 Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js 18+
    echo 下载地址: https://nodejs.org/
    pause
    exit /b 1
)

echo [1/5] 安装 Python 依赖...
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if %errorlevel% neq 0 (
    echo [警告] 清华镜像安装失败，尝试默认源...
    pip install -r requirements.txt
)

echo.
echo [2/5] 下载语义嵌入模型（首次需要，约90MB）...
set HF_ENDPOINT=https://hf-mirror.com
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); print('模型下载完成')"
if %errorlevel% neq 0 (
    echo [警告] 模型下载失败，系统将在首次搜索时自动重试
    echo 如果网络不通，请设置代理: set HTTPS_PROXY=你的代理地址
)

echo.
echo [3/5] 安装前端依赖...
cd web
call npm install --registry=https://registry.npmmirror.com
if %errorlevel% neq 0 (
    echo [警告] npm镜像安装失败，尝试默认源...
    call npm install
)
cd ..

echo.
echo [4/5] 构建前端生产版本...
cd web
call npx vite build
cd ..

echo.
echo [5/5] 创建必要目录...
if not exist "index" mkdir index
if not exist "generated" mkdir generated

echo.
echo ============================================
echo   安装完成！
echo ============================================
echo.
echo 启动方式:
echo   开发模式:  双击 start-dev.bat
echo   生产模式:  双击 start-prod.bat
echo.
echo 首次使用请编辑 config.yaml 配置:
echo   - LLM API 地址和密钥
echo   - 知识库存储路径
echo.
pause
