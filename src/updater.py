import os
import subprocess
import sys

GIT_TIMEOUT = 10

UPDATE_REPO = "https://github.com/mfxa48792/bw-cms-uploader.git"

# 不參與自動更新的本地分支（開發用）
DEV_BRANCHES = {"develop", "main", "master"}


def _run(args, timeout=GIT_TIMEOUT):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _latest_remote_tag() -> str | None:
    """取得遠端最新的 tag 名稱（依版本排序）。"""
    result = _run(["git", "ls-remote", "--tags", "--sort=-v:refname", UPDATE_REPO])
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        ref = line.split()[1]
        name = ref.replace("refs/tags/", "")
        if name.endswith("^{}"):
            name = name[:-3]
        return name
    return None


def check_for_updates():
    """檢查並自動更新程式（依最新 tag，來源為公開的 GitHub repo）。
    若有更新且更新成功，會 checkout 最新 tag 並重新啟動程式。
    """
    try:
        is_repo = _run(["git", "rev-parse", "--is-inside-work-tree"])
        if is_repo.returncode != 0 or is_repo.stdout.strip() != "true":
            print("[版本檢查] 非 git 安裝，略過自動更新")
            return

        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        if branch in DEV_BRANCHES:
            print(f"[版本檢查] 目前在開發分支（{branch}），略過自動更新")
            return

        latest_tag = _latest_remote_tag()
        if not latest_tag:
            print("[版本檢查] 無法連線更新伺服器或尚無發布版本，略過")
            return

        # 本地目前所在的 tag（若不在任何 tag 上則為 None）
        local_tag_result = _run(["git", "describe", "--tags", "--exact-match", "HEAD"])
        local_tag = local_tag_result.stdout.strip() if local_tag_result.returncode == 0 else None

        if local_tag == latest_tag:
            print(f"[版本檢查] 已是最新版本（{latest_tag}）")
            return

        # 本地有未提交變更時，不強行更新，避免覆蓋使用者修改（僅檢查本資料夾）
        status = _run(["git", "status", "--porcelain", "."]).stdout.strip()
        if status:
            print("[版本檢查] 偵測到本地有未提交的變更，略過自動更新")
            return

        print(f"[版本檢查] 發現新版本，正在更新（{local_tag or '未知版本'} → {latest_tag}）...")

        fetch = _run(["git", "fetch", "--quiet", "--tags", UPDATE_REPO], timeout=60)
        if fetch.returncode != 0:
            print(f"[版本檢查] 自動更新失敗，將使用目前版本：{fetch.stderr.strip()}")
            return

        checkout = _run(["git", "checkout", "--quiet", f"tags/{latest_tag}"], timeout=30)
        if checkout.returncode != 0:
            print(f"[版本檢查] 自動更新失敗，將使用目前版本：{checkout.stderr.strip()}")
            return

        print("[版本檢查] 更新完成，重新啟動程式...\n")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except subprocess.TimeoutExpired:
        print("[版本檢查] 連線逾時，略過更新")
    except FileNotFoundError:
        print("[版本檢查] 未偵測到 git，略過更新")
    except Exception as e:
        print(f"[版本檢查] 更新檢查發生錯誤，略過：{e}")
