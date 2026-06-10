import sys
import subprocess

MIN_PYTHON = (3, 10)

REQUIRED_PACKAGES = [
    ("playwright", "playwright"),
    ("requests", "requests"),
]


def check_python_version():
    if sys.version_info < MIN_PYTHON:
        print(f"[錯誤] 需要 Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} 以上，目前版本為 {sys.version}")
        sys.exit(1)
    print(f"[OK] Python {sys.version.split()[0]}")


def install_package(pip_name: str):
    print(f"  正在安裝 {pip_name}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name, "--quiet"])
    print(f"  {pip_name} 安裝完成")


def check_packages():
    for import_name, pip_name in REQUIRED_PACKAGES:
        try:
            __import__(import_name)
            print(f"[OK] {pip_name}")
        except ImportError:
            print(f"[缺少] {pip_name}，開始自動安裝...")
            install_package(pip_name)


def check_playwright_browser():
    """確認 Playwright chromium 已安裝，否則自動執行 playwright install。"""
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        print("[OK] Playwright chromium")
    except Exception:
        print("[缺少] Playwright chromium，開始安裝瀏覽器...")
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("Playwright chromium 安裝完成")


def run():
    print("=== 環境檢查 ===\n")
    check_python_version()
    check_packages()
    check_playwright_browser()
    print("\n環境檢查完成，啟動程式...\n")


if __name__ == "__main__":
    run()
