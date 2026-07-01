import getpass
import json
import os
from src.logger import logger

CONFIG_PATH = "config.json"
REQUIRED_FIELDS = ["url", "username", "password"]
DEFAULTS = {
    "debug": 0,
    "default_channel": "財經",
}


def ensure_config() -> dict:
    """讀取設定，缺少必要欄位時引導使用者補填。"""
    config = {}

    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

    # 補填缺少的預設值
    for key, val in DEFAULTS.items():
        if key not in config:
            config[key] = val

    # 檢查必要欄位
    missing = [f for f in REQUIRED_FIELDS if not config.get(f)]
    if missing:
        logger.info("【首次設定】請輸入上稿系統資訊\n")
        if not config.get("url"):
            config["url"] = input("上稿系統網址：").strip()
        if not config.get("username"):
            config["username"] = input("帳號：").strip()
        if not config.get("password"):
            config["password"] = getpass.getpass("密碼：").strip()

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("設定已儲存\n")
    else:
        logger.info(f"已載入設定（帳號：{config['username']}）\n")

    return config
