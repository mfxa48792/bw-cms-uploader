import sys
from src.logger import logger
from src.setup import ensure_config
from src.zip_handler import select_zip
from src.progress_tracker import ProgressTracker
from src.browser import Browser
from src.uploader import Uploader


def main():
    logger.info("=== CMS 上稿工具 ===\n")

    # 1. 確認設定（帳密、網址）
    config = ensure_config()

    # 2. 啟動瀏覽器並登入
    browser = Browser(config)
    browser.login()

    # 3. 輸入期數
    issue = input("請輸入期數：").strip()
    while not issue:
        issue = input("期數不可為空，請重新輸入：").strip()
    logger.info(f"期數：{issue}\n")

    # 4. 驗證期數是否已在 CMS 建檔
    if not browser.verify_magazine(issue):
        return browser, config

    # 5. 選擇 ZIP 並解壓縮
    articles, zip_path = select_zip()
    if not articles:
        logger.info("沒有找到可上傳的文章，程式結束。")
        return browser, config

    # 6. 斷點續傳確認
    tracker = ProgressTracker(total=len(articles))
    tracker.check_resume()

    # 7. 逐篇上稿
    uploader = Uploader(browser, tracker, articles, issue=issue, zip_path=zip_path)
    uploader.run()

    logger.info("\n=== 全部完成 ===")
    return browser, config


if __name__ == "__main__":
    browser = None
    config = {}
    try:
        browser, config = main()
    except KeyboardInterrupt:
        logger.info("\n程式中斷。")
    except Exception as e:
        logger.exception(f"程式發生錯誤：{e}")
    finally:
        if browser:
            if config.get("debug", 1) == 1:
                logger.info("\n[Debug 模式] 瀏覽器保持開啟，關閉此視窗即可結束。")
                input("按 Enter 關閉程式與瀏覽器...")
            browser.close()
