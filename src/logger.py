import logging
import os
from datetime import datetime

LOGS_DIR = "logs"

# Log level 定義
# Console: INFO 以上（關鍵進度）
# File: DEBUG 以上（所有細節）

def setup_logger() -> logging.Logger:
    os.makedirs(LOGS_DIR, exist_ok=True)

    log_filename = os.path.join(LOGS_DIR, datetime.now().strftime("%Y%m%d_%H%M%S") + ".log")

    logger = logging.getLogger("cms")
    logger.setLevel(logging.DEBUG)

    # Console handler — 只顯示 INFO 以上
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # File handler — 記錄所有 DEBUG 細節
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", datefmt="%H:%M:%S"))

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    logger.debug(f"Log 檔案：{log_filename}")
    return logger


# 全域 logger，其他模組 import 使用
logger = setup_logger()
