# Mattermost 下載器

這是一個用於下載 Mattermost 頻道訊息和檔案的 Python 工具，支援批量下載和選擇性下載功能。

## 功能特色

- 🔐 支援密碼和 Token 兩種登入方式
- 🦊 自動從 Firefox 瀏覽器提取 Token
- 📁 支援下載頻道訊息、檔案和程式碼區塊
- 🎯 多種下載模式：全部下載、選擇性下載、按類型過濾
- 🔄 智能重試機制，避免下載卡死
- 🌐 跨平台支援 (Windows, macOS, Linux)
- 📊 詳細的下載進度和錯誤報告

## 系統需求

- Python 3.7+
- Mattermost 8.1.2+ (已針對此版本優化)

## 安裝

1. git Clone 或下載此專案
2. 安裝依賴套件：
```bash
pip install mattermostdriver
```

## 使用方法

### 1. 單頻道下載模式 (main.py)

```bash
python main.py
```

這是基本的下載模式，適合下載特定頻道：

1. **配置連線資訊**：
   - 輸入 Mattermost 伺服器地址
   - 選擇登入方式（密碼或 Token）
   - 設定是否下載檔案

2. **選擇團隊和頻道**：
   - 從可用團隊列表中選擇
   - 從頻道列表中選擇要下載的頻道

3. **開始下載**：
   - 程式會下載選定頻道的所有訊息和檔案
   - 結果儲存在 `results/YYYYMMDD/` 目錄中

### 2. 批量下載模式 (auto_download_all.py)

```bash
python auto_download_all.py
```

這是進階的批量下載模式，提供三種下載選項：

#### 選項 1：下載所有頻道
- 下載團隊中的所有頻道
- 適合完整備份

#### 選項 2：選擇特定頻道下載
- 支援多種選擇格式：
  - 單個頻道：`0,1,5`
  - 範圍選擇：`10-15`
  - 混合選擇：`0,1,5,10-15`
- 會顯示選中的頻道列表供確認

#### 選項 3：按類型過濾下載
- **D** - 直接訊息 (Direct Messages)
- **P** - 私人頻道 (Private Channels)
- **O** - 公開頻道 (Open/Public Channels)
- **G** - 群組頻道 (Group Channels)

輸入範例：
- `D,P` - 只下載直接訊息和私人頻道
- `O` - 只下載公開頻道
- `D,P,O,G` - 下載所有類型

## 配置選項

### 自動配置儲存

程式會詢問是否將配置儲存到 `config.json` 檔案中，下次執行時會自動載入：

```json
{
  "host": "your-mattermost-server.com",
  "port": 443,
  "login_mode": "token",
  "username": "your-username",
  "token": "your-token",
  "download_files": true
}
```

### 登入方式

#### 1. 密碼登入
- 輸入使用者名稱和密碼
- 密碼不會儲存在配置檔案中

#### 2. Token 登入
- **建議使用手動獲取 Token 的方式**
- 程式也支援從 Firefox 瀏覽器自動提取 Token，但建議手動獲取以確保穩定性

### 手動獲取 MMAUTHTOKEN 教學

**建議使用此方法獲取 Token：**

1. **開啟瀏覽器並登入 Mattermost**
   - 使用任何瀏覽器（Chrome、Firefox、Safari 等）
   - 正常登入您的 Mattermost 帳號

2. **開啟開發者工具**
   - **Chrome/Edge**: 按 `F12` 或右鍵選擇「檢查」
   - **Firefox**: 按 `F12` 或右鍵選擇「檢查元素」
   - **Safari**: 先在「偏好設定 > 進階」中啟用開發選單，然後按 `Option + Cmd + I`

3. **找到 Application/Storage 標籤**
   - **Chrome/Edge**: 點擊「Application」標籤
   - **Firefox**: 點擊「儲存」標籤
   - **Safari**: 點擊「儲存」標籤

4. **查看 Cookies**
   - 在左側面板中找到「Cookies」
   - 展開並選擇您的 Mattermost 網域（例如：`https://your-mattermost-server.com`）

5. **複製 MMAUTHTOKEN**
   - 在 Cookie 列表中找到名稱為 `MMAUTHTOKEN` 的項目
   - 複製其「Value」欄位的值
   - 這個值通常很長，類似：`abcd1234efgh5678...`

6. **在程式中使用**
   - 當程式詢問 Token 時，貼上剛才複製的值
   - 或將其儲存在 `config.json` 檔案中

### Firefox Token 自動提取（進階選項）

**注意：建議優先使用上述手動方法**

如果您已在 Firefox 中登入 Mattermost，程式可以嘗試自動提取 Token：

- **Windows**: 從 `%APPDATA%/Mozilla/Firefox/Profiles` 搜尋
- **macOS**: 從 `~/Library/Application Support/Firefox/Profiles` 搜尋
- **Linux**: 從 `~/.mozilla/firefox` 搜尋

**自動提取的限制：**
- 需要 Firefox 瀏覽器
- 可能因為權限問題失敗
- 在某些系統上可能不穩定

## 輸出格式

### 目錄結構
```
results/
└── YYYYMMDD/
    └── 頻道名稱/
        ├── 頻道名稱.json          # 頻道資料和訊息
        ├── 001_檔案名稱.pdf       # 下載的檔案
        ├── 002_code.txt          # 程式碼區塊
        └── ...
```

### JSON 格式
```json
{
  "channel": {
    "name": "channel-name",
    "display_name": "頻道顯示名稱",
    "id": "channel-id",
    "team": "team-name",
    "exported_at": "2024-01-01T12:00:00Z"
  },
  "posts": [
    {
      "idx": 0,
      "id": "post-id",
      "created": "2024-01-01T12:00:00Z",
      "username": "user-name",
      "message": "訊息內容",
      "root_id": "parent-post-id",
      "files": ["檔案名稱.pdf"]
    }
  ]
}
```

## 錯誤處理

### 檔案下載錯誤
- 自動重試最多 3 次
- 失敗的檔案會被跳過，不會中斷整個下載程序
- 詳細的錯誤訊息和狀態報告

### 使用者不存在錯誤
- 當訊息作者帳號已被刪除時，使用 User ID 作為使用者名稱
- 確保下載程序不會因為使用者資料問題而中斷

### 網路連線問題
- 提供清楚的錯誤訊息
- 支援手動重試

## 進階功能

### 日期範圍過濾
在配置檔案中添加日期過濾：
```json
{
  "after": "2024-01-01",
  "before": "2024-12-31"
}
```

### URL 智能處理
- 自動移除輸入的 `http://` 或 `https://` 前綴
- 支援自定義連接埠設定

## 疑難排解

### 常見問題

1. **Token 提取失敗**
   - 確保 Firefox 已登入 Mattermost
   - 檢查 Firefox 設定檔路徑
   - 手動輸入 Token

2. **檔案下載失敗**
   - 檢查網路連線
   - 確認有足夠的磁碟空間
   - 檢查檔案權限

3. **連線錯誤**
   - 確認伺服器地址正確
   - 檢查連接埠設定
   - 確認 Token 或密碼有效

### 相容性說明

此工具已針對 Mattermost 8.1.2 版本進行優化，包含以下改進：
- 使用 `login_id` 替代 `username` 參數
- 添加 `team_id` 到頻道資料
- 改進的異常處理機制
- 支援新的 API 回應格式

## 授權

本專案基於原始 [mattermost-dl](https://gist.github.com/RobertKrajewski/5847ce49333062ea4be1a08f2913288c) 專案進行改進和擴展。

## 貢獻

歡迎提交 Issue 和 Pull Request 來改進這個工具！