@echo off
chcp 65001 >nul
setlocal

REM ============================================================
REM  GoFilm-Python 一键启动脚本 (Windows 批处理)
REM  模式: 本机 Python 热更新开发 + Docker 运行 MySQL/Redis
REM  使用: 双击本文件即可运行
REM ============================================================

echo ============================================================
echo  请确保 Docker Desktop 已打开,且右下角显示 Engine running
echo ============================================================
timeout /t 3 /nobreak >nul

REM ---------- Docker 探活 ----------
docker info >nul 2>&1
if errorlevel 1 (
    echo [错误] 无法连接 Docker API,请先启动 Docker Desktop!
    pause
    exit /b 1
)
echo [0/8] Docker 已就绪

REM ---------- 1. 切换到脚本所在目录 ----------
cd /d "%~dp0"
echo [1/8] 当前目录: %cd%

REM ---------- 2. 创建/激活虚拟环境 ----------
if not exist ".venv\Scripts\activate.bat" (
    echo [2/8] 创建虚拟环境 .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
) else (
    echo [2/8] 虚拟环境已存在
)
call .venv\Scripts\activate.bat
echo [2/8] 虚拟环境已激活

REM ---------- 3. 清理错误依赖 ----------
echo [3/8] 清理 asyncmy 残留与 pip 缓存 ...
pip uninstall asyncmy -y >nul 2>&1
pip cache purge >nul 2>&1

REM ---------- 4. 安装依赖 ----------
echo [4/8] 安装/校验依赖 ...
python -m pip install --upgrade pip --disable-pip-version-check >nul
pip install --no-cache-dir aiomysql==0.2.0
pip install --no-cache-dir -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

REM ---------- 5. 准备 .env ----------
if not exist ".env" (
    echo [5/8] 复制 .env.example -^> .env
    copy /Y ".env.example" ".env" >nul
) else (
    echo [5/8] .env 已存在
)

REM ---------- 6. 启动 Docker 容器 ----------
echo [6/8] 启动 mysql + redis 容器 ...
docker compose up -d mysql redis
if errorlevel 1 (
    echo [错误] Docker 启动失败
    pause
    exit /b 1
)

REM ---------- 7. 等待数据库就绪 ----------
echo [7/8] 等待 15 秒,确保 MySQL/Redis 健康检查通过 ...
timeout /t 15 /nobreak >nul
echo [7/8] 等待完成

REM ---------- 8. 启动 FastAPI ----------
echo [8/8] 启动 FastAPI (uvicorn --reload) ...
echo  访问: http://127.0.0.1:8000/docs
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
if errorlevel 1 (
    echo [错误] uvicorn 启动失败
    pause
    exit /b 1
)

pause