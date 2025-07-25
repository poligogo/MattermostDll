#!/usr/bin/env python3
"""
自動下載所有頻道的腳本
這個腳本會自動下載指定團隊中的所有頻道，無需手動選擇
"""

import os
import sys
import json
import pathlib
import getpass
import logging
from datetime import datetime, date, timezone
from typing import Dict, Optional, Tuple
from mattermostdriver import Driver, exceptions


def should_download_file(filename: str, config: Dict) -> Tuple[bool, str]:
    """檢查檔案是否應該下載（基於副檔名過濾）"""
    excluded_extensions = config.get('excluded_extensions', [])
    if not excluded_extensions:
        return True, "no_filter"
    
    # 獲取檔案副檔名
    file_ext = os.path.splitext(filename)[1].lower()
    
    if file_ext in excluded_extensions:
        return False, f"excluded_extension_{file_ext}"
    
    return True, "allowed"


class IncrementalDownloadManager:
    """增量下載管理器"""
    
    def __init__(self, output_base: str):
        self.output_base = output_base
        self.sync_state_file = os.path.join(output_base, 'sync_state.json')
        self.sync_state = self._load_sync_state()
    
    def _load_sync_state(self) -> Dict:
        """載入同步狀態"""
        if os.path.exists(self.sync_state_file):
            try:
                with open(self.sync_state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return self._create_empty_sync_state()
        return self._create_empty_sync_state()
    
    def _create_empty_sync_state(self) -> Dict:
        """創建空的同步狀態"""
        return {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "last_full_sync": None,
            "channels_last_sync": {},
            "downloaded_files": {},  # file_id -> {"path": "", "hash": "", "timestamp": ""}
            "sync_history": []
        }
    
    def get_channel_last_sync_time(self, channel_id: str) -> Optional[float]:
        """獲取頻道的最後同步時間（Unix 時間戳）"""
        channel_info = self.sync_state['channels_last_sync'].get(channel_id)
        if channel_info and 'last_post_timestamp' in channel_info:
            # 將 ISO 格式轉換為 Unix 時間戳
            try:
                dt = datetime.fromisoformat(channel_info['last_post_timestamp'].replace('Z', '+00:00'))
                return dt.timestamp()
            except ValueError:
                return None
        return None
    
    def update_channel_sync_time(self, channel_id: str, channel_name: str, 
                                last_post_timestamp: str, last_post_id: str):
        """更新頻道的同步時間"""
        if channel_id not in self.sync_state['channels_last_sync']:
            self.sync_state['channels_last_sync'][channel_id] = {}
        
        self.sync_state['channels_last_sync'][channel_id].update({
            "channel_name": channel_name,
            "last_post_timestamp": last_post_timestamp,
            "last_sync_time": datetime.now().isoformat(),
            "last_post_id": last_post_id
        })
        self._save_sync_state()
    
    def is_file_downloaded(self, file_id: str) -> bool:
        """檢查檔案是否已下載"""
        return file_id in self.sync_state['downloaded_files']
    
    def mark_file_downloaded(self, file_id: str, file_path: str, file_hash: str = None):
        """標記檔案為已下載"""
        self.sync_state['downloaded_files'][file_id] = {
            "path": file_path,
            "hash": file_hash,
            "timestamp": datetime.now().isoformat()
        }
        self._save_sync_state()
    
    def _save_sync_state(self):
        """儲存同步狀態"""
        os.makedirs(os.path.dirname(self.sync_state_file), exist_ok=True)
        with open(self.sync_state_file, 'w', encoding='utf-8') as f:
            json.dump(self.sync_state, f, indent=2, ensure_ascii=False)
    
    def has_sync_history(self) -> bool:
        """檢查是否有同步歷史"""
        return bool(self.sync_state['channels_last_sync'])
    
    def clear_sync_state(self):
        """清空同步狀態（用於完整重新同步）"""
        self.sync_state = self._create_empty_sync_state()
        self._save_sync_state()


def find_mmauthtoken_firefox(host):
    """從 Firefox 瀏覽器中尋找 Mattermost 認證 token"""
    # Support both Windows and macOS
    if os.name == 'nt':  # Windows
        appdata_dir = pathlib.Path(os.environ["APPDATA"])
        profiles_dir = appdata_dir / "Mozilla/Firefox/Profiles"
    else:  # macOS/Linux
        home_dir = pathlib.Path(os.environ["HOME"])
        profiles_dir = home_dir / "Library/Application Support/Firefox/Profiles"
    
    cookie_files = profiles_dir.rglob("cookies.sqlite")

    all_tokens = []
    for cookie_file in cookie_files:
        try:
            import sqlite3
            conn = sqlite3.connect(str(cookie_file))
            cursor = conn.cursor()
            cursor.execute("SELECT name, value FROM moz_cookies WHERE host = ? AND name = 'MMAUTHTOKEN'", (host,))
            results = cursor.fetchall()
            for name, value in results:
                all_tokens.append(value)
            conn.close()
        except Exception as e:
            print(f"Error reading cookies from {cookie_file}: {e}")
            continue
    
    if all_tokens:
        return all_tokens[0]  # Return the first token found
    return None


def get_config_from_json(config_filename: str = "config.json") -> dict:
    """從 JSON 檔案載入配置"""
    config_path = pathlib.Path(config_filename)
    if not config_path.exists():
        return {}

    with config_path.open() as f:
        config = json.load(f)

    return config


def complete_config(config: dict, config_filename: str = "config.json") -> dict:
    """完成配置設定"""
    config_changed = False
    if config.get("host", False):
        print(f"Using host '{config['host']}' from config")
    else:
        host_input = input("Please input host/server address: ")
        # Remove http:// or https:// prefix if present
        if host_input.startswith("https://"):
            host_input = host_input[8:]
        elif host_input.startswith("http://"):
            host_input = host_input[7:]
        config["host"] = host_input
        config_changed = True

    if config.get("port", False):
        print(f"Using port '{config['port']}' from config")
    else:
        port_input = input("Please input port (default 443): ")
        config["port"] = int(port_input) if port_input else 443
        config_changed = True

    if config.get("login_mode", False):
        print(f"Using login mode '{config['login_mode']}' from config")
    else:
        login_mode = ""
        while login_mode not in ["password", "token"]:
            login_mode = input("Please input login_mode 'password' or 'token' (=Gitlab Oauth): ")
        config["login_mode"] = login_mode
        config_changed = True

    password = None
    if config["login_mode"] == "password":
        if config.get("username", False):
            print(f"Using username '{config['username']}' from config")
        else:
            config["username"] = input("Please input your username: ")
            config_changed = True

        password = getpass.getpass("Enter your password (hidden): ")
    else:
        if config.get("token", False):
            print(f"Using token '{config['token']}' from config")
        else:
            print("Are you logged-in into Mattermost using the Firefox Browser? "
                  "If so, token may be automatically extracted")
            dec = ""
            while not (dec == "y" or dec == "n"):
                dec = input("Try to find token automatically? y/n: ")

            token = None
            if dec == "y":
                token = find_mmauthtoken_firefox(config["host"])
            elif not token:
                token = input("Please input your login token (MMAUTHTOKEN): ")
            config["token"] = token
            config_changed = True

    if "download_files" in config:
        print(f"Download files set to '{config['download_files']}' from config")
    else:
        dec = ""
        while not (dec == "y" or dec == "n"):
            dec = input("Should files be downloaded? y/n: ")
        config["download_files"] = dec == "y"
        config_changed = True

    # 檔案副檔名過濾配置
    if "excluded_extensions" in config:
        print(f"Excluded file extensions from config: {', '.join(config['excluded_extensions'])}")
    else:
        print("\n=== 檔案副檔名過濾設定 ===")
        print("您可以設定要排除下載的檔案副檔名（例如：.exe, .msi, .zip）")
        extensions_input = input("請輸入要排除的副檔名，用逗號分隔（留空表示下載所有檔案）: ")
        if extensions_input.strip():
            # 處理使用者輸入的副檔名
            extensions = [ext.strip().lower() for ext in extensions_input.split(',')]
            # 確保副檔名以點開頭
            extensions = [ext if ext.startswith('.') else '.' + ext for ext in extensions if ext]
            config["excluded_extensions"] = extensions
            print(f"設定排除的副檔名: {', '.join(extensions)}")
        else:
            config["excluded_extensions"] = []
            print("未設定副檔名過濾，將下載所有檔案")
        config_changed = True

    # 增量下載配置
    if "enable_incremental_download" in config:
        print(f"Incremental download enabled: {config['enable_incremental_download']}")
    else:
        print("\n=== 增量下載設定 ===")
        print("增量下載功能可以只下載新的對話和檔案，避免重複下載")
        dec = ""
        while not (dec == "y" or dec == "n"):
            dec = input("是否啟用增量下載功能? y/n: ")
        config["enable_incremental_download"] = dec == "y"
        if config["enable_incremental_download"]:
            print("已啟用增量下載功能")
        else:
            print("已停用增量下載功能，將進行完整下載")
        config_changed = True

    if config_changed:
        dec = ""
        while not (dec == "y" or dec == "n"):
            dec = input("Config changed! Would you like to store your config (without password) to file? y/n: ")
        if dec == "y":
            with open(config_filename, "w") as f:
                json.dump(config, f, indent=2)

            print(f"Stored new config to {config_filename}")

    config["password"] = password
    return config


def connect(host: str, port: int, token: str = None, username: str = None, password: str = None) -> Driver:
    """連接到 Mattermost 伺服器"""
    d = Driver({
        'url': host,
        'port': port,
        'token': token,
        'login_id': username,
        'password': password,
        'scheme': 'https'
    })
    d.login()
    return d


def get_users(d: Driver):
    """獲取使用者資訊"""
    print("Getting users...")
    users = d.users.get_users()
    user_id_to_name = {user["id"]: user["username"] for user in users}
    my_user_id = d.users.get_user("me")["id"]
    return user_id_to_name, my_user_id


def select_team(d: Driver, my_user_id: str):
    """選擇團隊"""
    print("Downloading all team information... ", end="")
    teams = d.teams.get_user_teams(my_user_id)
    print(f"Found {len(teams)} teams!")
    if len(teams) == 1:
        team = teams[0]
        print(f"Only one team found: {team['name']}")
    else:
        for i_team, team in enumerate(teams):
            print(f"{i_team}\t{team['name']}\t({team['id']})")
        team_idx = int(input("Select team by idx: "))
        team = teams[team_idx]
        print(f"Selected team {team['name']}")
    return team


def process_single_post(post, i_post, user_id_to_name, d, output_base, download_files, before, after, 
                       config=None, file_stats=None, incremental_manager=None):
    """處理單個 post，返回處理後的 post 資料或 None（如果被日期過濾）"""
    
    # Filter posts by date range
    created = post["create_at"] / 1000
    if (before and created > before) or (after and created < after):
        return None  # 被日期過濾，返回 None

    user_id = post["user_id"]
    if user_id not in user_id_to_name:
        try:
                    user_id_to_name[user_id] = d.users.get_user(user_id)["username"]
                except exceptions.ResourceNotFound:
                    user_id_to_name[user_id] = user_id
    username = user_id_to_name[user_id]
    created_str = datetime.fromtimestamp(post["create_at"] / 1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    message = post["message"]
    simple_post = dict(idx=i_post, id=post["id"], created=created_str, username=username, message=message)
    if post.get("root_id"):
        simple_post["root_id"] = post["root_id"]

    # If a code block is given in the message, dump it to file
    if message.count("```") > 1:
        start_pos = message.find("```") + 3
        end_pos = message.rfind("```")

        cut = message[start_pos:end_pos]
        if not len(cut):
            print("Code has no length")
        else:
            # 生成基礎檔案名稱並檢查是否已存在
            base_filename = "%03d" % i_post + "_code.txt"
            filename = base_filename
            counter = 1
            while (output_base / filename).exists():
                filename = "%03d" % i_post + f"_code_({counter}).txt"
                counter += 1
            
            with open(output_base / filename, "wb") as f:
                f.write(cut.encode())
            
            if filename != base_filename:
                print(f"程式碼區塊已存在，儲存為: {filename}")

    # If any files are attached to the message, download each
    if "files" in post["metadata"]:
        filenames = []
        for file in post["metadata"]["files"]:
            filename = file["name"]
            file_id = file["id"]
            filenames.append(filename)
            
            if download_files:
                # 檢查檔案是否已下載（增量下載功能）
                if incremental_manager and incremental_manager.is_file_downloaded(file_id):
                    print(f"檔案已存在，跳過: {filename}")
                    if file_stats:
                        file_stats['skipped'] += 1
                        file_stats['skip_reasons']['already_downloaded'] = file_stats['skip_reasons'].get('already_downloaded', 0) + 1
                    continue
                
                # 檢查副檔名過濾
                should_download, skip_reason = should_download_file(filename, config or {})
                if not should_download:
                    print(f"跳過檔案 {filename}: 副檔名被排除 ({skip_reason})")
                    if file_stats:
                        file_stats['skipped'] += 1
                        file_stats['skip_reasons'][skip_reason] = file_stats['skip_reasons'].get(skip_reason, 0) + 1
                    continue
                
                # 生成基礎檔案名稱
                base_filename = "%03d" % i_post + "_" + file["name"]
                filename_to_save = base_filename
                
                # 檢查檔案是否已存在，如果存在則添加數字後綴
                counter = 1
                while (output_base / filename_to_save).exists():
                    name_parts = file["name"].rsplit('.', 1)
                    if len(name_parts) == 2:
                        # 有副檔名的情況
                        filename_to_save = "%03d" % i_post + "_" + name_parts[0] + f"_({counter})." + name_parts[1]
                    else:
                        # 沒有副檔名的情況
                        filename_to_save = "%03d" % i_post + "_" + file["name"] + f"_({counter})"
                    counter += 1
                
                print("Downloading", file["name"])
                if filename_to_save != base_filename:
                    print(f"  -> 檔案已存在，儲存為: {filename_to_save}")
                
                # 限制重試次數，避免無限迴圈
                max_retries = 3
                retry_count = 0
                resp = None
                download_success = False
                
                while retry_count < max_retries:
                    try:
                        resp = d.files.get_file(file["id"])
                        break
                    except Exception as e:
                        retry_count += 1
                        print(f"Downloading file failed (attempt {retry_count}/{max_retries}): {str(e)}")
                        if retry_count >= max_retries:
                            print(f"Failed to download {file['name']} after {max_retries} attempts, skipping...")
                            break
                
                # 只有成功下載才寫入檔案
                if resp is not None:
                    try:
                        # Mattermost Driver unfortunately parses json files to dicts
                        if isinstance(resp, dict):
                            with open(output_base / filename_to_save, "w") as f:
                                json.dump(resp, f)
                        elif isinstance(resp, list):
                            with open(output_base / filename_to_save, "w") as f:
                                json.dump(resp, f)
                        else:
                            with open(output_base / filename_to_save, "wb") as f:
                                f.write(resp.content)
                        print(f"Successfully downloaded {file['name']}")
                        download_success = True
                        
                        # 標記檔案為已下載（增量下載功能）
                        if incremental_manager:
                            file_path = str(output_base / filename_to_save)
                            incremental_manager.mark_file_downloaded(file_id, file_path)
                        
                    except Exception as e:
                        print(f"Failed to save file {file['name']}: {str(e)}")
                        download_success = False
                else:
                    print(f"Skipped downloading {file['name']} due to repeated failures")
                    download_success = False
                
                # 更新檔案統計
                if file_stats:
                    if download_success:
                        file_stats['downloaded'] += 1
                    else:
                        file_stats['skipped'] += 1
                        file_stats['skip_reasons']['download_failed'] = file_stats['skip_reasons'].get('download_failed', 0) + 1

        simple_post["files"] = filenames
    
    return simple_post


def export_channel(d: Driver, channel: str, user_id_to_name: Dict[str, str], output_base: str,
                   download_files: bool = True, before: str = None, after: str = None, 
                   config: Dict = None, file_stats: Dict = None, incremental_manager=None):
    """匯出頻道資料，包含檔案覆蓋防護和流式寫入"""
    # Sanitize channel name
    channel_name = channel["display_name"].replace("\\", "").replace("/", "")

    print("Exporting channel", channel_name)
    if after:
        after = datetime.strptime(after, '%Y-%m-%d').timestamp()
    if before:
        before = datetime.strptime(before, '%Y-%m-%d').timestamp()

    # Create output directory
    output_base = pathlib.Path(output_base) / channel_name
    output_base.mkdir(parents=True, exist_ok=True)
    
    # 準備 JSON 檔案輸出路徑
    filtered_channel_name = ''.join(filter(lambda ch: ch not in "?!/\\.;:*\"<>|", channel_name))
    base_output_filename = filtered_channel_name + ".json"
    output_filename = base_output_filename
    
    # 檢查 JSON 檔案是否已存在，如果存在則添加數字後綴
    counter = 1
    while (output_base / output_filename).exists():
        name_without_ext = filtered_channel_name
        output_filename = f"{name_without_ext}_({counter}).json"
        counter += 1
    
    output_filepath = output_base / output_filename
    
    # 開始流式寫入 JSON 檔案
    with open(output_filepath, "w", encoding='utf8') as json_file:
        # 寫入 JSON 開頭和頻道資訊
        json_file.write('{\n')
        json_file.write('  "channel": {\n')
        json_file.write(f'    "name": "{channel["name"]}",\n')
        json_file.write(f'    "display_name": "{channel["display_name"]}",\n')
        json_file.write(f'    "header": "{channel.get("header", "")}",\n')
        json_file.write(f'    "id": "{channel["id"]}",\n')
        json_file.write(f'    "team": "{d.teams.get_team(channel["team_id"])["name"]}",\n')
        json_file.write(f'    "team_id": "{channel["team_id"]}",\n')
        json_file.write(f'    "exported_at": "{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}"\n')
        json_file.write('  },\n')
        json_file.write('  "posts": [\n')
        json_file.flush()  # 立即寫入檔案
        
        # 分批處理 posts，減少記憶體佔用
        page = 0
        total_posts_processed = 0
        first_post = True
        
        while True:
            print(f"Requesting channel page {page}")
            posts = d.posts.get_posts_for_channel(channel["id"], params={"per_page": 200, "page": page})

            if len(posts["posts"]) == 0:
                # If no posts are returned, we have reached the end
                break

            # 處理當前頁面的 posts（按時間順序反轉）
            page_posts = [posts["posts"][post] for post in posts["order"]]
            page_posts.reverse()  # 按時間順序排列
            
            for post in page_posts:
                # 即時處理每個 post，減少記憶體佔用
                simple_post = process_single_post(post, total_posts_processed, user_id_to_name, d, 
                                                 output_base, download_files, before, after,
                                                 config, file_stats, incremental_manager)
                
                if simple_post is not None:  # 如果 post 通過日期過濾
                    if not first_post:
                        json_file.write(',\n')
                    else:
                        first_post = False
                    
                    # 寫入 post 資料
                    json.dump(simple_post, json_file, indent=4, ensure_ascii=False)
                    json_file.flush()  # 立即寫入檔案
                    
                total_posts_processed += 1
            
            page += 1
            print(f"Processed {total_posts_processed} posts so far...")
        
        # 寫入 JSON 結尾
        json_file.write('\n  ]\n')
        json_file.write('}\n')
        json_file.flush()
    
    print(f"Found and processed {total_posts_processed} posts")
    if output_filename != base_output_filename:
        print(f"頻道資料檔案已存在，儲存為: '{output_filepath}'")
    else:
        print(f"Exported channel data to '{output_filepath}'")


def setup_logging(output_base):
    """設置日誌記錄"""
    # 確保日誌目錄存在
    log_dir = os.path.join(output_base, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 設置日誌檔案名稱（包含時間戳）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"auto_download_{timestamp}.log")
    
    # 設置日誌格式
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # 創建無緩衝的檔案處理器，確保即時寫入
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # 創建控制台處理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # 配置日誌記錄器
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[file_handler, console_handler],
        force=True  # 強制重新配置
    )
    
    # 設置檔案處理器為無緩衝模式
    if hasattr(file_handler, 'stream'):
        # 強制每次寫入後立即刷新
        original_emit = file_handler.emit
        def flush_emit(record):
            original_emit(record)
            if hasattr(file_handler.stream, 'flush'):
                file_handler.stream.flush()
        file_handler.emit = flush_emit
    
    # 創建一個只輸出到檔案的 logger，設置即時寫入
    file_logger = logging.getLogger('file_only')
    file_logger.setLevel(logging.INFO)
    file_logger.handlers.clear()  # 清除繼承的 handlers
    file_only_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_only_handler.setFormatter(logging.Formatter(log_format, date_format))
    
    # 設置檔案專用處理器也為無緩衝模式
    if hasattr(file_only_handler, 'stream'):
        original_emit_file = file_only_handler.emit
        def flush_emit_file(record):
            original_emit_file(record)
            if hasattr(file_only_handler.stream, 'flush'):
                file_only_handler.stream.flush()
        file_only_handler.emit = flush_emit_file
    
    file_logger.addHandler(file_only_handler)
    file_logger.propagate = False  # 防止向上傳播
    
    logger = logging.getLogger(__name__)
    logger.info(f"日誌記錄已啟動，日誌檔案: {log_file}")
    return logger, file_logger, log_file

def log_and_print(logger, message, level='info'):
    """同時記錄到日誌和控制台的函數"""
    if level == 'info':
        logger.info(message)
    elif level == 'warning':
        logger.warning(message)
    elif level == 'error':
        logger.error(message)
    elif level == 'debug':
        logger.debug(message)

def auto_download_all_channels():
    """自動下載所有頻道"""
    print("=== 自動批量下載所有頻道 ===")
    
    # 載入配置
    config = get_config_from_json()
    config = complete_config(config)
    
    output_base = "results/" + date.today().strftime("%Y%m%d")
    
    # 設置日誌記錄
    logger, file_logger, log_file = setup_logging(output_base)
    
    # 初始化增量下載管理器
    incremental_manager = None
    if config.get('enable_incremental_download', False):
        incremental_manager = IncrementalDownloadManager(output_base)
        log_and_print(logger, "已啟用增量下載功能")
    
    # 初始化全域檔案統計
    global_file_stats = {
        'downloaded': 0,
        'skipped': 0,
        'skip_reasons': {}
    }
    
    log_and_print(logger, "=== 自動批量下載所有頻道 ===")
    log_and_print(logger, f"儲存下載資料到 {output_base}")
    log_and_print(logger, f"日誌檔案位置: {log_file}")
    
    # 日期範圍過濾
    after = config.get("after", None)
    before = config.get("before", None)
    
    if after:
        log_and_print(logger, f"設定開始日期過濾: {after}")
    if before:
        log_and_print(logger, f"設定結束日期過濾: {before}")
    
    # 連接到 Mattermost
    log_and_print(logger, "正在連接到 Mattermost...")
    d = connect(config["host"], config.get("port", 443), config.get("token", None),
                config.get("username", None), config.get("password", None))
    log_and_print(logger, "成功連接到 Mattermost")
    
    # 獲取使用者資訊
    log_and_print(logger, "正在獲取使用者資訊...")
    user_id_to_name, my_user_id = get_users(d)
    log_and_print(logger, f"獲取到 {len(user_id_to_name)} 個使用者資訊")
    
    # 選擇團隊
    log_and_print(logger, "正在選擇團隊...")
    team = select_team(d, my_user_id)
    log_and_print(logger, f"選擇團隊: {team.get('display_name', team.get('name', 'Unknown'))}")
    
    # 獲取所有頻道
    log_and_print(logger, "正在下載所有頻道資訊...")
    channels = d.channels.get_channels_for_user(my_user_id, team["id"])
    log_and_print(logger, f"獲取到 {len(channels)} 個頻道")
    
    # 為直接訊息添加顯示名稱
    for channel in channels:
        channel["team_id"] = team["id"]
        if channel["type"] != "D":
            continue
        # 頻道名稱由兩個使用者 ID 用雙底線連接組成
        user_ids = channel["name"].split("__")
        other_user_id = user_ids[1] if user_ids[0] == my_user_id else user_ids[0]
        if other_user_id in user_id_to_name:
            channel["display_name"] = user_id_to_name[other_user_id]
        else:
            # 如果找不到使用者名稱，使用 ID
            channel["display_name"] = f"Unknown_User_{other_user_id}"
    
    # 按名稱排序頻道
    channels = sorted(channels, key=lambda x: x["display_name"].lower())
    
    log_and_print(logger, f"找到 {len(channels)} 個頻道！")
    
    # 檢查增量下載歷史
    sync_mode = "full"
    if incremental_manager and incremental_manager.has_sync_history():
        log_and_print(logger, "\n=== 發現同步歷史 ===")
        log_and_print(logger, f"已同步的頻道數: {len(incremental_manager.sync_state['channels_last_sync'])}")
        
        choice = ""
        while choice not in ["i", "f", "s"]:
            choice = input("請選擇同步模式 (i=增量同步, f=完整重新同步, s=選擇性同步): ").lower()
        
        if choice == "i":
            log_and_print(logger, "使用增量同步模式...")
            sync_mode = "incremental"
        elif choice == "f":
            log_and_print(logger, "使用完整重新同步模式...")
            sync_mode = "full"
            # 清空同步狀態
            incremental_manager.clear_sync_state()
        else:
            log_and_print(logger, "使用選擇性同步模式...")
            sync_mode = "selective"
    elif incremental_manager:
        log_and_print(logger, "首次同步，將進行完整下載...")
        sync_mode = "full"
    
    # 頻道列表顯示（控制台不顯示時間戳，但記錄到日誌）
    print("\n頻道列表：")
    file_logger.info("頻道列表：")
    for i, channel in enumerate(channels):
        channel_info = f"{i:3d}\t{channel['display_name']}\t({channel['type']})"
        print(channel_info)  # 控制台顯示，無時間戳
        file_logger.info(f"頻道 {i}: {channel['display_name']} ({channel['type']})")  # 日誌記錄
    
    # 詢問下載模式
    log_and_print(logger, "\n請選擇下載模式：")
    log_and_print(logger, "1. 下載所有頻道")
    log_and_print(logger, "2. 選擇特定頻道下載")
    log_and_print(logger, "3. 按類型過濾下載")
    log_and_print(logger, "4. 排除特定頻道，下載其餘所有頻道")
    
    mode = input("請輸入選項 (1/2/3/4): ")
    log_and_print(logger, f"使用者選擇模式: {mode}")
    
    if mode == "1":
        # 下載所有頻道
        log_and_print(logger, "選擇下載所有頻道")
        confirm = input(f"\n確定要下載所有 {len(channels)} 個頻道嗎？ (y/n): ")
        log_and_print(logger, f"使用者確認: {confirm}")
        if confirm.lower() != 'y':
            log_and_print(logger, "使用者取消下載")
            return
        filtered_channels = channels
        log_and_print(logger, f"將下載所有 {len(filtered_channels)} 個頻道")
        
    elif mode == "2":
        # 選擇特定頻道
        log_and_print(logger, "選擇特定頻道下載模式")
        print("\n請輸入要下載的頻道編號，用逗號分隔 (例如: 0,1,5,10-15):")
        selection = input("頻道編號: ")
        log_and_print(logger, f"使用者輸入的頻道編號: {selection}")
        
        try:
            selected_indices = []
            for part in selection.split(','):
                part = part.strip()
                if '-' in part:
                    # 處理範圍 (例如: 10-15)
                    start, end = map(int, part.split('-'))
                    selected_indices.extend(range(start, end + 1))
                else:
                    # 處理單個編號
                    selected_indices.append(int(part))
            
            # 去重並排序
            selected_indices = sorted(set(selected_indices))
            log_and_print(logger, f"解析後的頻道編號: {selected_indices}")
            
            # 驗證編號範圍
            invalid_indices = [i for i in selected_indices if i < 0 or i >= len(channels)]
            if invalid_indices:
                error_msg = f"錯誤：無效的頻道編號: {invalid_indices}"
                log_and_print(logger, error_msg, 'error')
                log_and_print(logger, f"有效範圍: 0-{len(channels)-1}", 'error')
                return
            
            filtered_channels = [channels[i] for i in selected_indices]
            log_and_print(logger, f"\n已選擇 {len(filtered_channels)} 個頻道：")
            for ch in filtered_channels:
                channel_info = f"  - {ch['display_name']} ({ch['type']})"
                log_and_print(logger, channel_info)
                
        except ValueError as e:
            error_msg = "錯誤：請輸入有效的數字格式"
            log_and_print(logger, f"{error_msg} - {str(e)}", 'error')
            return
            
    elif mode == "3":
        # 按類型過濾
        log_and_print(logger, "選擇按類型過濾下載模式")
        log_and_print(logger, "\n頻道類型說明：")
        log_and_print(logger, "D - 直接訊息 (Direct Messages)")
        log_and_print(logger, "P - 私人頻道 (Private Channels)")
        log_and_print(logger, "O - 公開頻道 (Open/Public Channels)")
        log_and_print(logger, "G - 群組頻道 (Group Channels)")
        
        type_input = input("\n請輸入要下載的頻道類型，用逗號分隔 (例如: D,P 或 O,G): ")
        log_and_print(logger, f"使用者輸入的頻道類型: {type_input}")
        
        try:
            # 解析使用者輸入的類型
            selected_types = [t.strip().upper() for t in type_input.split(',')]
            log_and_print(logger, f"解析後的頻道類型: {selected_types}")
            
            # 驗證類型是否有效
            valid_types = ['D', 'P', 'O', 'G']
            invalid_types = [t for t in selected_types if t not in valid_types]
            if invalid_types:
                error_msg = f"錯誤：無效的頻道類型: {invalid_types}"
                log_and_print(logger, error_msg, 'error')
                log_and_print(logger, f"有效類型: {', '.join(valid_types)}", 'error')
                return
            
            # 過濾頻道
            filtered_channels = [ch for ch in channels if ch['type'] in selected_types]
            log_and_print(logger, f"\n選擇的類型: {', '.join(selected_types)}")
            log_and_print(logger, f"過濾後將下載 {len(filtered_channels)} 個頻道")
            
            if len(filtered_channels) == 0:
                log_and_print(logger, "沒有符合條件的頻道", 'warning')
                return
            
            # 顯示將要下載的頻道
            log_and_print(logger, "\n將要下載的頻道：")
            for ch in filtered_channels[:10]:  # 只顯示前10個
                channel_info = f"  - {ch['display_name']} ({ch['type']})"
                log_and_print(logger, channel_info)
            if len(filtered_channels) > 10:
                log_and_print(logger, f"  ... 還有 {len(filtered_channels) - 10} 個頻道")
                
            confirm = input(f"\n確定要下載這 {len(filtered_channels)} 個頻道嗎？ (y/n): ")
            log_and_print(logger, f"使用者確認: {confirm}")
            if confirm.lower() != 'y':
                log_and_print(logger, "使用者取消下載")
                return
                
        except Exception as e:
            error_msg = f"錯誤：輸入格式不正確 - {str(e)}"
            log_and_print(logger, error_msg, 'error')
            log_and_print(logger, "請使用格式：D,P 或 O,G", 'error')
            return
            
    elif mode == "4":
        # 排除特定頻道，下載其餘所有頻道
        log_and_print(logger, "選擇排除特定頻道下載模式")
        print("\n請輸入要排除的頻道編號，用逗號分隔 (例如: 0,1,5,10-15):")
        exclusion = input("要排除的頻道編號: ")
        log_and_print(logger, f"使用者輸入要排除的頻道編號: {exclusion}")
        
        try:
            excluded_indices = []
            if exclusion.strip():  # 如果有輸入排除的頻道
                for part in exclusion.split(','):
                    part = part.strip()
                    if not part:  # 跳過空白部分
                        continue
                    if '-' in part:
                        # 處理範圍 (例如: 10-15)
                        range_parts = part.split('-')
                        if len(range_parts) != 2:
                            raise ValueError(f"無效的範圍格式: {part}")
                        start, end = map(int, range_parts)
                        if start > end:
                            raise ValueError(f"範圍起始值不能大於結束值: {part}")
                        excluded_indices.extend(range(start, end + 1))
                    else:
                        # 處理單個編號
                        excluded_indices.append(int(part))
                
                # 去重並排序
                excluded_indices = sorted(set(excluded_indices))
                log_and_print(logger, f"解析後要排除的頻道編號: {excluded_indices}")
                
                # 驗證編號範圍
                invalid_indices = [i for i in excluded_indices if i < 0 or i >= len(channels)]
                if invalid_indices:
                    error_msg = f"錯誤：無效的頻道編號: {invalid_indices}"
                    log_and_print(logger, error_msg, 'error')
                    log_and_print(logger, f"有效範圍: 0-{len(channels)-1}", 'error')
                    return
            else:
                # 如果沒有輸入任何排除的頻道，提示使用者
                log_and_print(logger, "沒有輸入要排除的頻道，將下載所有頻道")
            
            # 建立要下載的頻道清單（排除指定的頻道）
            filtered_channels = [channels[i] for i in range(len(channels)) if i not in excluded_indices]
            
            # 檢查是否還有頻道可以下載
            if len(filtered_channels) == 0:
                log_and_print(logger, "錯誤：排除所有頻道後沒有剩餘頻道可下載", 'warning')
                return
            
            log_and_print(logger, f"\n排除 {len(excluded_indices)} 個頻道後，將下載 {len(filtered_channels)} 個頻道：")
            
            # 顯示被排除的頻道
            if excluded_indices:
                log_and_print(logger, "\n被排除的頻道：")
                for idx in excluded_indices[:10]:  # 只顯示前10個
                    excluded_info = f"  - {channels[idx]['display_name']} ({channels[idx]['type']})"
                    log_and_print(logger, excluded_info)
                if len(excluded_indices) > 10:
                    log_and_print(logger, f"  ... 還有 {len(excluded_indices) - 10} 個被排除的頻道")
            
            # 顯示將要下載的頻道（前10個）
            log_and_print(logger, "\n將要下載的頻道：")
            for ch in filtered_channels[:10]:  # 只顯示前10個
                channel_info = f"  - {ch['display_name']} ({ch['type']})"
                log_and_print(logger, channel_info)
            if len(filtered_channels) > 10:
                log_and_print(logger, f"  ... 還有 {len(filtered_channels) - 10} 個頻道")
                
            confirm = input(f"\n確定要下載這 {len(filtered_channels)} 個頻道嗎？ (y/n): ")
            log_and_print(logger, f"使用者確認: {confirm}")
            if confirm.lower() != 'y':
                log_and_print(logger, "使用者取消下載")
                return
                
        except ValueError as e:
            error_msg = "錯誤：請輸入有效的數字格式"
            log_and_print(logger, f"{error_msg} - {str(e)}", 'error')
            return
        except Exception as e:
            error_msg = f"錯誤：輸入格式不正確 - {str(e)}"
            log_and_print(logger, error_msg, 'error')
            return
            
    else:
        log_and_print(logger, "無效的選項", 'error')
        return
    
    # 開始批量下載
    log_and_print(logger, f"\n=== 開始{sync_mode}下載 {len(filtered_channels)} 個頻道 ===")
    
    # 顯示檔案過濾設定
    if config.get('excluded_extensions'):
        log_and_print(logger, f"檔案過濾設定: 排除 {', '.join(config['excluded_extensions'])} 檔案")
    else:
        log_and_print(logger, "檔案過濾設定: 下載所有檔案")
    
    failed_channels = []
    total_new_posts = 0
    total_new_files = 0
    
    for i_channel, channel in enumerate(filtered_channels):
        try:
            progress_msg = f"\n[{i_channel + 1}/{len(filtered_channels)}] 開始匯出頻道: {channel['display_name']}"
            log_and_print(logger, progress_msg)
            
            # 重置頻道級別的檔案統計
            channel_file_stats = {
                'downloaded': 0,
                'skipped': 0,
                'skip_reasons': {}
            }
            
            export_channel(d, channel, user_id_to_name, output_base, 
                         config["download_files"], before, after, 
                         config, channel_file_stats, incremental_manager)
            
            # 更新全域統計
            global_file_stats['downloaded'] += channel_file_stats['downloaded']
            global_file_stats['skipped'] += channel_file_stats['skipped']
            for reason, count in channel_file_stats['skip_reasons'].items():
                global_file_stats['skip_reasons'][reason] = global_file_stats['skip_reasons'].get(reason, 0) + count
            
            success_msg = f"✓ 完成匯出: {channel['display_name']} (下載 {channel_file_stats['downloaded']} 檔案, 跳過 {channel_file_stats['skipped']} 檔案)"
            log_and_print(logger, success_msg)
            
        except Exception as e:
            error_msg = f"✗ 匯出失敗: {channel['display_name']} - 錯誤: {str(e)}"
            log_and_print(logger, error_msg, 'error')
            failed_channels.append((channel['display_name'], str(e)))
            
            # 詢問是否繼續
            continue_download = input("是否繼續下載其他頻道？ (y/n): ")
            log_and_print(logger, f"使用者選擇是否繼續: {continue_download}")
            if continue_download.lower() != 'y':
                log_and_print(logger, "使用者選擇停止下載")
                break
    
    # 顯示結果摘要
    log_and_print(logger, "\n=== 下載完成摘要 ===")
    log_and_print(logger, f"總頻道數: {len(channels)}")
    log_and_print(logger, f"嘗試下載: {len(filtered_channels)}")
    log_and_print(logger, f"成功下載: {len(filtered_channels) - len(failed_channels)}")
    log_and_print(logger, f"失敗數量: {len(failed_channels)}")
    
    # 檔案統計報告
    log_and_print(logger, "\n=== 檔案下載統計 ===")
    log_and_print(logger, f"總共下載檔案: {global_file_stats['downloaded']} 個")
    log_and_print(logger, f"總共跳過檔案: {global_file_stats['skipped']} 個")
    
    if global_file_stats['skip_reasons']:
        log_and_print(logger, "\n跳過檔案原因統計:")
        for reason, count in global_file_stats['skip_reasons'].items():
            log_and_print(logger, f"  - {reason}: {count} 個")
    
    # 保存增量下載狀態
    if incremental_manager:
        incremental_manager.save_sync_state()
        log_and_print(logger, "增量下載狀態已保存")
    
    if failed_channels:
        print("\n=== 失敗的頻道清單 ===")
        log_and_print(logger, "\n失敗的頻道：", 'warning')
        
        # 在控制台清楚顯示失敗的頻道名稱
        print("\n以下頻道下載失敗，可用於後續重新下載：")
        failed_channel_names = []
        for i, (channel_name, error) in enumerate(failed_channels, 1):
            print(f"{i:2d}. {channel_name}")
            failed_channel_names.append(channel_name)
            # 詳細錯誤信息記錄到日誌
            failure_info = f"  - {channel_name}: {error}"
            log_and_print(logger, failure_info, 'warning')
        
        # 輸出失敗頻道名稱清單，方便複製
        print("\n失敗頻道名稱清單（可複製用於重新下載）：")
        print(", ".join(failed_channel_names))
        print("="*50)
    
    log_and_print(logger, f"\n所有資料已儲存到: {output_base}")
    log_and_print(logger, f"日誌檔案位置: {log_file}")
    log_and_print(logger, "批量下載完成！")

if __name__ == '__main__':
    try:
        auto_download_all_channels()
    except KeyboardInterrupt:
        print("\n\n使用者中斷下載")
        # 嘗試記錄到日誌（如果日誌已設置）
        try:
            logger = logging.getLogger(__name__)
            if logger.handlers:
                logger.info("使用者中斷下載")
        except:
            pass
        sys.exit(1)
    except Exception as e:
        error_msg = f"\n發生錯誤: {str(e)}"
        print(error_msg)
        # 嘗試記錄到日誌（如果日誌已設置）
        try:
            logger = logging.getLogger(__name__)
            if logger.handlers:
                logger.error(f"程式執行發生錯誤: {str(e)}")
        except:
            pass
        sys.exit(1)