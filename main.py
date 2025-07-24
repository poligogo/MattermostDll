import os
import sqlite3
from datetime import datetime, date, timezone
from typing import Tuple, Dict, List
import getpass

from mattermostdriver import Driver, exceptions
import pathlib
import json


def connect(host: str, port: int = 443, login_token: str = None, username: str = None, password: str = None) -> Driver:
    d = Driver({
        "url": host,
        "port": port,
        "token": login_token,
        "login_id": username,
        "password": password
    })
    d.login()
    return d


def get_users(d: Driver) -> Tuple[Dict[str, str], str]:
    my_user = d.users.get_user("me")
    my_username = my_user["username"]
    my_user_id = my_user["id"]
    print(f"Successfully logged in as {my_username} ({my_user_id})")

    # Get all usernames as we want to use those instead of the user ids
    user_id_to_name = {}
    page = 0
    print("Downloading all user information... ", end="")
    while True:
        users_resp = d.users.get_users(params={"per_page": 200, "page": page})
        if len(users_resp) == 0:
            break
        for user in users_resp:
            user_id_to_name[user["id"]] = user["username"]
        page += 1
    print(f"Found {len(user_id_to_name)} users!")

    return user_id_to_name, my_user_id


def select_team(d: Driver, my_user_id: str) -> str:
    print("Downloading all team information... ", end="")
    teams = d.teams.get_user_teams(my_user_id)
    print(f"Found {len(teams)} teams!")
    for i_team, team in enumerate(teams):
        print(f"{i_team}\t{team['name']}\t({team['id']})")
    team_idx = int(input("Select team by idx: "))
    team = teams[team_idx]
    print(f"Selected team {team['name']}")
    return team


def select_channel(d: Driver, team: str, my_user_id: str, user_id_to_name: Dict[str, str],
                   verbose: bool = False) -> List[str]:
    print("Downloading all channel information... ", end="")
    channels = d.channels.get_channels_for_user(my_user_id, team["id"])
    # Add display name to direct messages
    for channel in channels:
        channel["team_id"] = team["id"]
        if channel["type"] != "D":
            continue

        # The channel name consists of two user ids connected by a double underscore
        user_ids = channel["name"].split("__")
        other_user_id = user_ids[1] if user_ids[0] == my_user_id else user_ids[0]
        channel["display_name"] = user_id_to_name[other_user_id]
    # Sort channels by name for easier search
    channels = sorted(channels, key=lambda x: x["display_name"].lower())
    print(f"Found {len(channels)} channels!")

    for i_channel, channel in enumerate(channels):
        if verbose:
            channel_id = f"\t({channel['id']})"
        else:
            channel_id = ""
        print(f"{i_channel}\t{channel['display_name']}{channel_id}")
    channel_input = input("Select channels by idx separated by comma or type 'all' for downloading all channels: ")
    if channel_input == "all":
        channel_idxs = list(range(len(channels)))
    else:
        channel_idxs = channel_input.replace(" ", "").split(",")
    selected_channels = [channels[int(idx)] for idx in channel_idxs]
    print("Selected channel(s):", ", ".join([channel["display_name"] for channel in selected_channels]))
    return selected_channels


def export_channel(d: Driver, channel: str, user_id_to_name: Dict[str, str], output_base: str,
                   download_files: bool = True, before: str = None, after: str = None):
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
                                                 output_base, download_files, before, after)
                
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


def process_single_post(post, i_post, user_id_to_name, d, output_base, download_files, before, after):
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
            if download_files:
                # 生成基礎檔案名稱
                base_filename = "%03d" % i_post + "_" + file["name"]
                filename = base_filename
                
                # 檢查檔案是否已存在，如果存在則添加數字後綴
                counter = 1
                while (output_base / filename).exists():
                    name_parts = file["name"].rsplit('.', 1)
                    if len(name_parts) == 2:
                        # 有副檔名的情況
                        filename = "%03d" % i_post + "_" + name_parts[0] + f"_({counter})." + name_parts[1]
                    else:
                        # 沒有副檔名的情況
                        filename = "%03d" % i_post + "_" + file["name"] + f"_({counter})"
                    counter += 1
                
                print("Downloading", file["name"])
                if filename != base_filename:
                    print(f"  -> 檔案已存在，儲存為: {filename}")
                
                # 限制重試次數，避免無限迴圈
                max_retries = 3
                retry_count = 0
                resp = None
                
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
                            with open(output_base / filename, "w") as f:
                                json.dump(resp, f)
                        elif isinstance(resp, list):
                            with open(output_base / filename, "w") as f:
                                json.dump(resp, f)
                        else:
                            with open(output_base / filename, "wb") as f:
                                f.write(resp.content)
                        print(f"Successfully downloaded {file['name']}")
                    except Exception as e:
                        print(f"Failed to save file {file['name']}: {str(e)}")
                else:
                    print(f"Skipped downloading {file['name']} due to repeated failures")

            filenames.append(file["name"])
        simple_post["files"] = filenames
    
    return simple_post


def get_config_from_json(config_filename: str = "config.json") -> dict:
    config_path = pathlib.Path(config_filename)
    if not config_path.exists():
        return {}

    with config_path.open() as f:
        config = json.load(f)

    return config


def complete_config(config: dict, config_filename: str = "config.json") -> dict:
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


def find_mmauthtoken_firefox(host):
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
        print(f"Opening {cookie_file}")
        connection = sqlite3.connect(str(cookie_file))
        cursor = connection.cursor()
        rows = cursor.execute("SELECT host, value FROM moz_cookies WHERE name = 'MMAUTHTOKEN'").fetchall()
        all_tokens.extend(rows)

    all_tokens = [token for token in all_tokens if host in token[0]]

    print(f"Found {len(all_tokens)} token for {host}")
    for token in all_tokens:
        print(f"{token[0]}: {token[1]}")

    if len(all_tokens) > 1:
        print("Using first token!")

    if len(all_tokens):
        return all_tokens[0][1]
    else:
        return None


if __name__ == '__main__':
    config = get_config_from_json()
    config = complete_config(config)

    output_base = "results/" + date.today().strftime("%Y%m%d")
    print(f"Storing downloaded data in {output_base}")

    # Range of posts to be exported as string in format "YYYY-MM-DD". Use None if no filter should be applied
    after = config.get("after", None)
    before = config.get("before", None)

    d = connect(config["host"], config.get("port", 443), config.get("token", None),
                config.get("username", None), config.get("password", None))
    user_id_to_name, my_user_id = get_users(d)
    team = select_team(d, my_user_id)
    channels = select_channel(d, team, my_user_id, user_id_to_name)
    for i_channel, channel in enumerate(channels):
        print(f"Start export of channel {i_channel + 1}/{len(channels)}")
        export_channel(d, channel, user_id_to_name, output_base, config["download_files"],
                       before, after)
    print("Finished export")