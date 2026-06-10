import os
import json
import zipfile
import shutil
from glob import glob

INBOX_DIR = "inbox"
TEMP_DIR = "temp"


def _extract_zip(zip_path: str):
    """解壓縮 ZIP，自動處理 Windows cp950 / Mac utf-8 中文路徑。"""
    if os.path.exists(TEMP_DIR):
        shutil.rmtree(TEMP_DIR)
    os.makedirs(TEMP_DIR)

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            try:
                member.filename = member.filename.encode("cp437").decode("cp950")
            except Exception:
                try:
                    member.filename = member.filename.encode("cp437").decode("utf-8")
                except Exception:
                    pass
            zf.extract(member, TEMP_DIR)


def _read_json(path: str) -> list | dict | None:
    """讀取 JSON 檔，自動偵測編碼。"""
    if not os.path.exists(path):
        return None
    for enc in ["utf-8-sig", "utf-8", "cp950"]:
        try:
            with open(path, encoding=enc) as f:
                return json.load(f)
        except Exception:
            continue
    return None


def _read_txt(path: str) -> str | None:
    """讀取 txt 檔，自動偵測編碼。"""
    if not os.path.exists(path):
        return None
    for enc in ["utf-8-sig", "utf-8", "cp950"]:
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except Exception:
            continue
    return None


def _parse_articles() -> list[dict]:
    """掃描 temp/ 找出所有文章資料夾並載入資料。"""
    articles = []

    # ZIP 解壓後第一層是期數資料夾（如 2013/），第二層才是文章資料夾
    for issue_dir in sorted(os.listdir(TEMP_DIR)):
        issue_path = os.path.join(TEMP_DIR, issue_dir)
        if not os.path.isdir(issue_path):
            continue

        for article_dir in sorted(os.listdir(issue_path)):
            article_path = os.path.join(issue_path, article_dir)
            if not os.path.isdir(article_path):
                continue

            article = {
                "id": article_dir,
                "path": article_path,
                "field": _read_json(os.path.join(article_path, "field.json")),
                "article_txt": _read_txt(os.path.join(article_path, "article.txt")),
                "ds_img": {
                    "dir": os.path.join(article_path, "DS_IMG"),
                    "meta": _read_json(os.path.join(article_path, "DS_IMG", "meta.json")),
                },
                "ds_box": {
                    "dir": os.path.join(article_path, "DS_BOX"),
                    "meta": _read_json(os.path.join(article_path, "DS_BOX", "meta.json")),
                    "img": {
                        "dir": os.path.join(article_path, "DS_BOX", "IMG"),
                        "meta": _read_json(os.path.join(article_path, "DS_BOX", "IMG", "meta.json")),
                    },
                },
            }

            articles.append(article)

    return articles


def select_zip() -> tuple[list[dict], str] | tuple[None, None]:
    """
    掃描 inbox，讓使用者選擇 ZIP，解壓縮後回傳 (文章清單, ZIP路徑)。
    失敗時回傳 (None, None)。
    """
    zips = glob(os.path.join(INBOX_DIR, "*.zip"))

    if not zips:
        print("inbox/ 資料夾中沒有 ZIP 檔，請放入後重新執行。")
        return None, None

    if len(zips) == 1:
        chosen = zips[0]
        print(f"偵測到 ZIP：{os.path.basename(chosen)}")
    else:
        print("偵測到多個 ZIP，請選擇：")
        for i, z in enumerate(zips, 1):
            print(f"  {i}. {os.path.basename(z)}")
        while True:
            try:
                idx = int(input("輸入編號：")) - 1
                if 0 <= idx < len(zips):
                    chosen = zips[idx]
                    break
            except ValueError:
                pass
            print("請輸入有效的編號")

    # 若 temp/ 已存在（斷點續傳）則跳過解壓縮，保留已替換的內容
    if os.path.exists(TEMP_DIR) and os.listdir(TEMP_DIR):
        print("偵測到上次未清理的 temp/，跳過解壓縮直接續用\n")
    else:
        print("正在解壓縮...")
        _extract_zip(chosen)
        print(f"已解壓縮到 temp/\n")

    articles = _parse_articles()
    if not articles:
        print("ZIP 內找不到任何文章資料夾。")
        return None, None

    print(f"共找到 {len(articles)} 篇文章：")
    for i, a in enumerate(articles, 1):
        print(f"  {i}. {a['id']}")
    print()

    return articles, chosen
