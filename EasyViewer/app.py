#!/usr/bin/env python3
"""
Mattermost 聊天記錄查看器
簡易的 Web 介面來查看下載的聊天記錄
"""

import os
import json
import glob
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_from_directory
from pathlib import Path
from urllib.parse import unquote

app = Flask(__name__)

# 設定結果資料夾路徑
RESULTS_BASE_PATH = Path('../results')

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
def index():
    """主頁面"""
    dates = get_available_dates()
    return render_template('index.html', dates=dates)

@app.route('/api/channels/<date>')
def get_channels(date):
    """API: 獲取指定日期的頻道列表"""
    channels = get_channels_for_date(date)
    return jsonify(channels)

@app.route('/api/channel/<date>/<path:channel_name>/<json_filename>')
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
    app.run(debug=True, host='0.0.0.0', port=5002)