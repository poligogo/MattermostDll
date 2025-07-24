#!/bin/bash

# Mattermost 聊天記錄查看器啟動腳本

echo "=== Mattermost 聊天記錄查看器 ==="
echo "正在啟動 Web 介面..."
echo ""

# 檢查是否安裝了依賴套件
if [ ! -d "venv" ]; then
    echo "建議創建虛擬環境："
    echo "python -m venv venv"
    echo "source venv/bin/activate"
    echo "pip install -r requirements.txt"
    echo ""
fi

# 檢查 Python 和 Flask
if ! command -v python &> /dev/null; then
    echo "錯誤：找不到 Python"
    exit 1
fi

if ! python -c "import flask" &> /dev/null; then
    echo "正在安裝依賴套件..."
    pip install -r requirements.txt
fi

# 啟動應用程式
echo "啟動 Web 伺服器..."
echo "請在瀏覽器中開啟: http://localhost:5001"
echo "按 Ctrl+C 停止伺服器"
echo ""

python app.py