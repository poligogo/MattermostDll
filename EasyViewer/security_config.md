# EasyViewer 安全配置指南

## 概述

EasyViewer 現在包含了輕量化的安全機制，保護您的 Mattermost 聊天記錄不被未授權存取。

## 安全功能

### 1. 密碼認證系統
- 所有頁面都需要密碼驗證才能存取
- 支援自訂密碼設定和強度要求
- 密碼錯誤會顯示詳細提示訊息
- 支援密碼變更功能
- 密碼加密儲存和驗證

### 2. 進階 Session 管理
- 登入後 Session 有效期為 1 小時（可自訂）
- Session 過期會自動重新導向到登入頁面
- 支援手動登出功能
- Session 安全性增強，防止會話劫持
- 自動清理過期 Session

### 3. 安全監控與提示
- 登入頁面包含安全使用提示
- 主頁面顯示當前安全狀態
- 登出時會有確認提示
- 登入失敗次數監控
- 安全事件日誌記錄

### 4. 資料保護
- 搜尋資料記憶體保護機制
- 自動清理敏感資料
- 防止資料洩露的安全措施
- 檔案存取權限控制

## 配置方式

### 方法一：環境變數（推薦）

```bash
# 設定存取密碼
export ACCESS_PASSWORD="your_secure_password_here"

# 設定 Session 超時時間（秒）
export SESSION_TIMEOUT="7200"  # 2小時

# 設定 Flask 密鑰（用於 Session 加密）
export SECRET_KEY="your_secret_key_here"

# 啟動應用程式
python app.py
```

### 方法二：修改程式碼

編輯 `app.py` 檔案中的以下行：

```python
# 修改預設密碼
ACCESS_PASSWORD = os.environ.get('ACCESS_PASSWORD', 'your_new_password')

# 修改 Session 超時時間（秒）
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', '7200'))  # 2小時
```

## 安全建議

### 1. 密碼安全策略
- 使用強密碼（至少 12 個字元）
- 包含大小寫字母、數字和特殊字元
- 定期更換密碼（建議每 3-6 個月）
- 不要使用預設密碼 `mattermost2024`
- 避免使用常見密碼或個人資訊
- 考慮使用密碼管理器

### 2. 網路安全
- 建議在內網環境中使用
- 如需外網存取，請配置 HTTPS
- 考慮使用 VPN 或其他網路安全措施
- 限制存取 IP 範圍
- 使用防火牆保護

### 3. 伺服器安全
- 定期更新系統和相依套件
- 限制伺服器存取權限
- 監控存取日誌和異常活動
- 定期備份重要資料
- 使用最小權限原則

### 4. 使用習慣與最佳實踐
- 使用完畢後記得登出
- 不要在公共電腦上保存密碼
- 不要分享存取密碼
- 定期檢查登入記錄
- 避免在不安全的網路環境下使用
- 注意瀏覽器安全設定

### 5. 資料安全
- 定期清理瀏覽器快取和 Cookie
- 避免在搜尋中輸入敏感資訊
- 注意全域搜尋的資料範圍
- 適當限制記憶體使用量
- 定期檢查系統資源使用情況

## 進階安全選項

### 1. HTTPS 配置

如需 HTTPS 支援，可以使用 nginx 或 Apache 作為反向代理：

```nginx
server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/certificate.crt;
    ssl_certificate_key /path/to/private.key;
    
    location / {
        proxy_pass http://127.0.0.1:5005;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 2. IP 白名單

可以在 `app.py` 中添加 IP 限制：

```python
from flask import request, abort

ALLOWED_IPS = ['127.0.0.1', '192.168.1.0/24']  # 允許的 IP 範圍

@app.before_request
def limit_remote_addr():
    if request.remote_addr not in ALLOWED_IPS:
        abort(403)  # Forbidden
```

### 3. 存取日誌

啟用 Flask 的存取日誌記錄：

```python
import logging
from logging.handlers import RotatingFileHandler

if not app.debug:
    file_handler = RotatingFileHandler('access.log', maxBytes=10240, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
```

### 4. 搜尋資料保護

為了保護搜尋過程中的敏感資料，可以配置以下安全措施：

```python
# 在 app.py 中添加記憶體保護設定
MAX_SEARCH_MEMORY = 100 * 1024 * 1024  # 100MB 限制
MAX_CHANNELS_LOAD = 20  # 最多載入 20 個頻道
MAX_MESSAGES_PER_CHANNEL = 1000  # 每個頻道最多 1000 條訊息

# 搜尋資料自動清理
@app.route('/api/clear_search_cache', methods=['POST'])
def clear_search_cache():
    # 清理搜尋快取的 API 端點
    return jsonify({'status': 'success', 'message': '搜尋快取已清理'})
```

### 5. 會話安全增強

強化會話管理的安全性：

```python
# 設定更安全的 Session 配置
app.config.update(
    SESSION_COOKIE_SECURE=True,  # 僅在 HTTPS 下傳送
    SESSION_COOKIE_HTTPONLY=True,  # 防止 XSS 攻擊
    SESSION_COOKIE_SAMESITE='Lax',  # 防止 CSRF 攻擊
    PERMANENT_SESSION_LIFETIME=timedelta(hours=1)  # 會話超時
)
```

## 故障排除

### 常見問題

1. **忘記密碼**
   - 檢查環境變數 `ACCESS_PASSWORD`
   - 或修改 `app.py` 中的預設密碼
   - 使用密碼變更功能重設密碼

2. **Session 過期太快**
   - 調整 `SESSION_TIMEOUT` 環境變數
   - 單位為秒，預設 3600（1小時）
   - 檢查會話安全設定

3. **無法存取**
   - 確認防火牆設定
   - 檢查 IP 限制設定
   - 查看應用程式日誌
   - 驗證 HTTPS 憑證（如有使用）

4. **全域搜尋效能問題**
   - 檢查記憶體使用量是否超過限制
   - 調整 `MAX_CHANNELS_LOAD` 和 `MAX_MESSAGES_PER_CHANNEL` 參數
   - 清理搜尋快取資料
   - 重新整理頁面釋放記憶體

5. **搜尋資料載入失敗**
   - 確認網路連線穩定
   - 檢查瀏覽器記憶體限制
   - 查看瀏覽器開發者工具的錯誤訊息
   - 嘗試減少搜尋範圍

6. **安全警告或錯誤**
   - 檢查 HTTPS 設定
   - 驗證 Session 配置
   - 查看安全事件日誌
   - 確認密碼強度符合要求

### 重設安全設定

如需重設所有安全設定，可以：

1. 停止應用程式
2. 清除環境變數
3. 重新設定密碼和其他參數
4. 重新啟動應用程式

## 更新日誌

- **v1.1.0**: 新增基本密碼認證和 Session 管理
- **v1.1.1**: 改善登入介面和安全提示
- **v1.1.2**: 新增登出功能和 Session 狀態顯示
- **v3.0.0**: 重大安全功能更新
  - 🔐 強化密碼認證系統，支援密碼變更
  - 🛡️ 進階 Session 管理和安全性增強
  - 📊 新增搜尋資料保護機制
  - 🔒 記憶體安全管理和自動清理
  - 📈 效能監控和資源限制
  - 🚨 安全事件日誌和監控
  - 🌐 HTTPS 和網路安全配置支援
  - 🎯 全域搜尋安全保護措施

---

**注意**: 這是一個輕量化的安全機制，適用於內網或小型團隊使用。如需更高級的安全功能，建議考慮使用專業的身份認證系統。