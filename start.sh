#!/bin/bash
set -e  # 遇到错误立即退出

# ===================== 配置项（根据实际情况修改）=====================
APP_NAME="app.py"          # 你的Python脚本名
PID_FILE="./app.pid"       # PID文件路径（记录进程ID，用于停止/重启）
LOG_FILE="./app.log"       # 日志文件路径（记录脚本输出）
PYTHON_CMD="poetry run python3 app.py"       # Python解释器（若用虚拟环境，改为虚拟环境路径，如 ./venv/bin/python3）
WORK_DIR=$(pwd)            # 工作目录（脚本和app.py所在目录）
# ====================================================================

# 检查进程是否运行
check_running() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        # 检查PID对应的进程是否存在
        if ps -p "$PID" > /dev/null 2>&1; then
            return 0  # 运行中
        else
            rm -f "$PID_FILE"  # PID文件存在但进程已死，清理文件
            return 1  # 未运行
        fi
    else
        return 1  # 未运行
    fi
}

# 启动脚本
start() {
    if check_running; then
        echo -e "\033[33m[$APP_NAME] 已在运行（PID: $(cat $PID_FILE)）\033[0m"
        return 0
    fi

    echo -e "\033[32m[$APP_NAME] 正在启动...\033[0m"
    # 后台运行Python脚本，输出重定向到日志，记录PID到文件
    cd "$WORK_DIR"
    nohup $PYTHON_CMD "$APP_NAME" > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"

    # 验证启动是否成功
    sleep 1
    if check_running; then
        echo -e "\033[32m[$APP_NAME] 启动成功（PID: $(cat $PID_FILE)），日志文件：$LOG_FILE\033[0m"
    else
        echo -e "\033[31m[$APP_NAME] 启动失败，请查看日志：$LOG_FILE\033[0m"
        rm -f "$PID_FILE"
        exit 1
    fi
}

# 停止脚本
stop() {
    if ! check_running; then
        echo -e "\033[33m[$APP_NAME] 未运行\033[0m"
        return 0
    fi

    PID=$(cat "$PID_FILE")
    echo -e "\033[32m[$APP_NAME] 正在停止（PID: $PID）...\033[0m"
    
    # 先尝试优雅停止（SIGTERM），失败则强制停止（SIGKILL）
    kill "$PID" > /dev/null 2>&1 || {
        echo -e "\033[33m[$APP_NAME] 优雅停止失败，强制停止...\033[0m"
        kill -9 "$PID" > /dev/null 2>&1 || {
            echo -e "\033[31m[$APP_NAME] 强制停止失败（PID: $PID）\033[0m"
            exit 1
        }
    }

    # 清理PID文件
    rm -f "$PID_FILE"
    echo -e "\033[32m[$APP_NAME] 停止成功\033[0m"
}

# 重启脚本
restart() {
    echo -e "\033[32m[$APP_NAME] 正在重启...\033[0m"
    stop
    sleep 1
    start
    echo -e "\033[32m[$APP_NAME] 重启完成\033[0m"
}

# 查看状态
status() {
    if check_running; then
        echo -e "\033[32m[$APP_NAME] 运行中（PID: $(cat $PID_FILE)）\033[0m"
    else
        echo -e "\033[31m[$APP_NAME] 未运行\033[0m"
    fi
}

# 帮助信息
usage() {
    echo "用法：$0 {start|stop|restart|status}"
    echo "  start   - 启动 $APP_NAME"
    echo "  stop    - 停止 $APP_NAME"
    echo "  restart - 重启 $APP_NAME"
    echo "  status  - 查看 $APP_NAME 运行状态"
    exit 1
}

# 主逻辑：根据参数执行对应操作
case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    *)
        usage
        ;;
esac