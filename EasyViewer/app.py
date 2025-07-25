#!/usr/bin/env python3
"""
Mattermost 聊天記錄查看器
簡易的 Web 介面來查看下載的聊天記錄
"""

import os
import json
import glob
import secrets
from datetime import datetime, timedelta
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, flash
from pathlib import Path
from urllib.parse import unquote
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# 安全設定
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'mattermost2024')  # 預設密碼，建議透過環境變數設定
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', '3600'))  # Session 超時時間（秒），預設1小時

# 設定結果資料夾路徑
RESULTS_BASE_PATH = Path('../results')

def require_auth(f):
    """認證裝飾器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 檢查是否已登入
        if 'authenticated' not in session:
            return redirect(url_for('login'))
        
        # 檢查 session 是否過期
        if 'login_time' in session:
            login_time = datetime.fromisoformat(session['login_time'])
            if datetime.now() - login_time > timedelta(seconds=SESSION_TIMEOUT):
                session.clear()
                flash('登入已過期，請重新登入', 'warning')
                return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登入頁面"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ACCESS_PASSWORD:
            session['authenticated'] = True
            session['login_time'] = datetime.now().isoformat()
            flash('登入成功！', 'success')
            return redirect(url_for('index'))
        else:
            flash('密碼錯誤，請重試', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    flash('已成功登出', 'info')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@require_auth
def change_password():
    """修改密碼"""
    global ACCESS_PASSWORD
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # 驗證當前密碼
        if current_password != ACCESS_PASSWORD:
            flash('當前密碼錯誤', 'error')
            return render_template('change_password.html')
        
        # 驗證新密碼
        if not new_password or len(new_password) < 6:
            flash('新密碼至少需要 6 個字元', 'error')
            return render_template('change_password.html')
        
        if new_password != confirm_password:
            flash('新密碼確認不一致', 'error')
            return render_template('change_password.html')
        
        # 更新密碼（僅在當前 session 中有效）
        ACCESS_PASSWORD = new_password
        
        # 清除所有 session，強制重新登入
        session.clear()
        
        flash('密碼已成功更新，請使用新密碼重新登入', 'success')
        return redirect(url_for('login'))
    
    return render_template('change_password.html')

def get_available_dates():
    """獲取可用的日期資料夾"""
    dates = []
    if RESULTS_BASE_PATH.exists():
        for date_folder in RESULTS_BASE_PATH.iterdir():
            if date_folder.is_dir() and date_folder.name.isdigit() and len(date_folder.name) == 8:
                dates.append(date_folder.name)
    return sorted(dates, reverse=True)

def get_channels_for_date(date):
    """獲取指定日期的所有頻道"""
    channels = []
    date_path = RESULTS_BASE_PATH / date
    if date_path.exists():
        for channel_folder in date_path.iterdir():
            if channel_folder.is_dir():
                # 尋找 JSON 檔案
                json_files = list(channel_folder.glob('*.json'))
                if json_files:
                    channels.append({
                        'name': channel_folder.name,
                        'path': str(channel_folder),
                        'json_file': json_files[0].name
                    })
    return sorted(channels, key=lambda x: x['name'].lower())

def load_channel_data(date, channel_name, json_filename):
    """載入頻道的聊天資料"""
    json_path = RESULTS_BASE_PATH / date / channel_name / json_filename
    
    print(f"Trying to load: {json_path}")
    print(f"Path exists: {json_path.exists()}")
    
    if not json_path.exists():
        print(f"File not found: {json_path}")
        return None
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 處理訊息資料
        posts = data.get('posts', [])
        
        # 按時間排序
        posts.sort(key=lambda x: x.get('created', ''))
        
        # 處理每個訊息
        for post in posts:
            # 格式化時間
            if 'created' in post:
                try:
                    dt = datetime.fromisoformat(post['created'].replace('Z', '+00:00'))
                    post['formatted_time'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                    post['time_only'] = dt.strftime('%H:%M')
                except:
                    post['formatted_time'] = post['created']
                    post['time_only'] = post['created']
            
            # 處理訊息內容中的換行
            if 'message' in post:
                post['message_html'] = post['message'].replace('\n', '<br>')
            
            # 檢查附件檔案是否存在
            if 'files' in post:
                post['existing_files'] = []
                for filename in post['files']:
                    # 尋找實際的檔案（可能有數字後綴）
                    file_pattern = f"{post['idx']:03d}_*{filename}*"
                    matching_files = list((RESULTS_BASE_PATH / date / channel_name).glob(file_pattern))
                    if matching_files:
                        post['existing_files'].append({
                            'original_name': filename,
                            'actual_name': matching_files[0].name,
                            'exists': True
                        })
                    else:
                        post['existing_files'].append({
                            'original_name': filename,
                            'actual_name': filename,
                            'exists': False
                        })
        
        return {
            'channel': data.get('channel', {}),
            'posts': posts,
            'total_posts': len(posts)
        }
    
    except Exception as e:
        print(f"Error loading channel data from {json_path}: {e}")
        import traceback
        traceback.print_exc()
        return None

@app.route('/')
@require_auth
def index():
    """主頁面"""
    dates = get_available_dates()
    return render_template('index.html', dates=dates)

@app.route('/api/channels/<date>')
@require_auth
def get_channels(date):
    """API: 獲取指定日期的頻道列表"""
    channels = get_channels_for_date(date)
    return jsonify(channels)

@app.route('/api/channel/<date>/<path:channel_name>/<json_filename>')
@require_auth
def get_channel_data(date, channel_name, json_filename):
    """API: 獲取頻道聊天資料"""
    try:
        # URL 解碼
        channel_name = unquote(channel_name)
        json_filename = unquote(json_filename)
        
        data = load_channel_data(date, channel_name, json_filename)
        if data:
            return jsonify(data)
        else:
            return jsonify({'error': f'Channel data not found: {channel_name}/{json_filename}'}), 404
    except Exception as e:
        return jsonify({'error': f'Error loading channel: {str(e)}'}), 500

@app.route('/files/<date>/<path:channel_name>/<filename>')
@require_auth
def serve_file(date, channel_name, filename):
    """提供檔案下載"""
    try:
        # URL 解碼
        channel_name = unquote(channel_name)
        filename = unquote(filename)
        
        file_path = RESULTS_BASE_PATH / date / channel_name
        return send_from_directory(file_path, filename)
    except Exception as e:
        return jsonify({'error': f'File not found: {str(e)}'}), 404

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🔐 EasyViewer 安全模式已啟用")
    print("="*60)
    
    if ACCESS_PASSWORD == 'mattermost2024':
        print("⚠️  警告：正在使用預設密碼！")
        print("   🔑 當前密碼：mattermost2024 (固定不變)")
        print("   💡 如要更改密碼，請重新啟動並設定：")
        print("      export ACCESS_PASSWORD=\"你的新密碼\" && python app.py")
    else:
        print("✅ 已設定自訂密碼")
        print(f"   🔑 當前密碼已設定 (重啟前不會改變)")
    
    print(f"\n🕐 Session 有效期：{SESSION_TIMEOUT // 60} 分鐘")
    print("🌐 存取網址：http://127.0.0.1:5005")
    print("\n💡 密碼說明：")
    print("   • 密碼在服務運行期間保持不變")
    print("   • 忘記密碼時，停止服務重新啟動即可")
    print("   • 重啟時可重新設定 ACCESS_PASSWORD 環境變數")
    print("📖 詳細說明：請參考 README_安全設定.md")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5005)