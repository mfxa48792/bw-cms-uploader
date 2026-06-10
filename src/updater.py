import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

VERSION_FILE = "VERSION"
RELEASES_API = "https://api.github.com/repos/mfxa48792/bw-cms-uploader/releases/latest"

# 更新時不覆蓋的本地資料
EXCLUDE = {
    "config.json", "logs", "done", "temp", "inbox", "progress.json",
    ".git", "__pycache__",
}

REQUEST_HEADERS = {"User-Agent": "cms-uploader-updater"}


def _read_local_version() -> str | None:
    if not os.path.exists(VERSION_FILE):
        return None
    with open(VERSION_FILE, encoding="utf-8") as f:
        return f.read().strip()


def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _download(url: str, dest_path: str, timeout: int = 60):
    req = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as f:
        shutil.copyfileobj(resp, f)


def check_for_updates():
    """檢查並自動更新程式（GitHub Releases，僅用標準函式庫，不需git/requests）。
    若有新版本，下載並覆蓋程式檔案後重新啟動。
    """
    try:
        local_version = _read_local_version()

        try:
            data = _http_get_json(RELEASES_API)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print("[版本檢查] 尚無發布版本，略過")
            else:
                print(f"[版本檢查] 更新檢查失敗（HTTP {e.code}），略過")
            return
        except urllib.error.URLError as e:
            print(f"[版本檢查] 無法連線更新伺服器，略過：{e.reason}")
            return

        remote_version = data.get("tag_name")
        if not remote_version:
            print("[版本檢查] 找不到版本資訊，略過")
            return

        if local_version == remote_version:
            print(f"[版本檢查] 已是最新版本（{remote_version}）")
            return

        zip_url = data.get("zipball_url")
        if not zip_url:
            print("[版本檢查] 找不到下載連結，略過")
            return

        print(f"[版本檢查] 發現新版本，正在更新（{local_version or '未知版本'} → {remote_version}）...")

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = os.path.join(tmpdir, "update.zip")
            _download(zip_url, zip_path)

            extract_dir = os.path.join(tmpdir, "extracted")
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)

            # GitHub zipball 內只有一層根資料夾
            root_items = os.listdir(extract_dir)
            if len(root_items) != 1:
                print("[版本檢查] 更新檔案結構異常，略過")
                return
            src_root = os.path.join(extract_dir, root_items[0])

            for name in os.listdir(src_root):
                if name in EXCLUDE:
                    continue
                src_path = os.path.join(src_root, name)
                dst_path = os.path.join(".", name)
                if os.path.isdir(dst_path):
                    shutil.rmtree(dst_path)
                elif os.path.exists(dst_path):
                    os.remove(dst_path)
                shutil.move(src_path, dst_path)

        print("[版本檢查] 更新完成，重新啟動程式...\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except Exception as e:
        print(f"[版本檢查] 更新檢查發生錯誤，略過：{e}")
