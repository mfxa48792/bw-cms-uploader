import csv
import json
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from src.browser import Browser
from src.progress_tracker import ProgressTracker
from src.logger import logger

INBOX_DIR = "inbox"
DONE_DIR = "done"
TEMP_DIR = "temp"


class Uploader:
    def __init__(self, browser: Browser, tracker: ProgressTracker, articles: list[dict], issue: str = "", zip_path: str = ""):
        self.browser = browser
        self.tracker = tracker
        self.articles = articles
        self.issue = issue
        self.zip_path = zip_path
        self.csv_rows: list[dict] = []

    def run(self):
        total = len(self.articles)
        start = self.tracker.current_article

        for idx in range(start, total):
            article = self.articles[idx]
            logger.info(f"\n--- 第 {idx + 1}/{total} 篇 ---")
            logger.debug(f"文章資料夾：{article['id']}")

            if self.tracker.articles.get(str(idx)) == "done":
                logger.debug("已完成，跳過")
                continue

            self._upload_article(idx, article)
            self.tracker.mark_article_done(idx)
            logger.info(f"第 {idx + 1} 篇完成")

        self._finalize(debug=self.browser.config.get("debug", 1) == 1)

    def _upload_article(self, idx: int, article: dict):
        """單篇文章完整上稿流程。"""
        has_box = bool(article["ds_box"]["meta"])
        total_steps = 2 + (1 if has_box else 0)
        start_step = self.tracker.current_step if idx == self.tracker.current_article else 0

        steps = [
            lambda a=article, t=total_steps: self._phase_ds_img(a, t),
            *([ lambda a=article, t=total_steps: self._phase_ds_box(a, t) ] if has_box else []),
            lambda a=article, t=total_steps: self._create_article(a, t),
        ]

        for step_idx, step_fn in enumerate(steps[start_step:], start=start_step):
            step_fn()
            self.tracker.mark_step(idx, step_idx)

        return steps

    # ── 第一步：DS_IMG ───────────────────────────────────────

    def _phase_ds_img(self, article: dict, total_steps: int):
        ds_img_meta = article["ds_img"]["meta"] or []
        pending = [item for item in ds_img_meta if not item.get("cms_id")]
        total = len(ds_img_meta)
        logger.info(f"  步驟 1/{total_steps} - 上傳圖片")

        if not pending:
            logger.debug("所有圖片已上傳，跳過")
            return

        # 取得上傳憑證
        site_id, cookies = self.browser.get_gallery_credentials()

        # 並行上傳所有待處理圖片
        img_name_map = {}  # file → img_name
        with ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(
                    self.browser.post_image_file,
                    os.path.join(article["ds_img"]["dir"], item["file"]),
                    site_id,
                    cookies,
                ): item for item in pending
            }
            for future in as_completed(futures):
                item = futures[future]
                img_name = future.result()
                img_name_map[item["file"]] = img_name
                logger.debug(f"上傳完成 {item['file']} → {img_name}")

        # 一次進 Gallery 頁面逐筆填資料
        self.browser._goto("Gallery/Index")
        self.browser.page.reload(wait_until="domcontentloaded")

        for i, img_item in enumerate(ds_img_meta, 1):
            logger.info(f"    ({i}/{total}) {img_item['file']}")

            if img_item.get("cms_id"):
                logger.debug(f"已跳過（cms_id={img_item['cms_id']}）")
                continue

            img_name = img_name_map[img_item["file"]]
            cms_id, cms_guid, _ = self.browser.fill_image_row(
                img_name=img_name,
                title=img_item.get("title", ""),
                desc=img_item.get("desc", ""),
                author_label=img_item.get("author_label", ""),
                author_value=img_item.get("author_value", ""),
            )

            img_item["cms_id"] = cms_id
            img_item["cms_guid"] = cms_guid
            self._save_meta(article["ds_img"]["dir"], article["ds_img"]["meta"])

            article["article_txt"] = self._replace_placeholder(
                article["article_txt"], img_item["file"], cms_id
            )
            logger.debug(f"替換佔位符 {{{img_item['file']}}} → {{DS_IMG_{cms_id}}}")
            self._save_txt(os.path.join(article["path"], "article.txt"), article["article_txt"])

    # ── 第二步：DS_BOX ───────────────────────────────────────

    def _phase_ds_box(self, article: dict, total_steps: int):
        step_no = total_steps - 1
        logger.info(f"  步驟 {step_no}/{total_steps} - 上傳BOX")

        # 先上傳 DS_BOX/IMG（並行）
        ds_box_img_meta = article["ds_box"]["img"]["meta"] or []
        pending_box_img = [item for item in ds_box_img_meta if not item.get("cms_id")]

        if pending_box_img:
            site_id, cookies = self.browser.get_gallery_credentials()

            box_img_name_map = {}
            with ThreadPoolExecutor() as executor:
                futures = {
                    executor.submit(
                        self.browser.post_image_file,
                        os.path.join(article["ds_box"]["img"]["dir"], item["file"]),
                        site_id,
                        cookies,
                    ): item for item in pending_box_img
                }
                for future in as_completed(futures):
                    item = futures[future]
                    img_name = future.result()
                    box_img_name_map[item["file"]] = img_name

            # 一次進 Gallery 填資料
            self.browser._goto("Gallery/Index")
            self.browser.page.reload(wait_until="domcontentloaded")

            for img_item in ds_box_img_meta:
                if img_item.get("cms_id"):
                    continue
                img_name = box_img_name_map[img_item["file"]]
                cms_id, cms_guid, img_url = self.browser.fill_image_row(
                    img_name=img_name,
                    title=img_item.get("title", ""),
                    desc=img_item.get("desc", ""),
                    author_label=img_item.get("author_label", ""),
                    author_value=img_item.get("author_value", ""),
                )
                img_item["cms_id"] = cms_id
                img_item["cms_guid"] = cms_guid
                self._save_meta(article["ds_box"]["img"]["dir"], article["ds_box"]["img"]["meta"])

                img_tag = f'<img src="{img_url}">'
                box_meta = article["ds_box"]["meta"] or []
                for box_item in box_meta:
                    txt_path = os.path.join(article["ds_box"]["dir"], box_item["file"])
                    content = self._read_txt(txt_path)
                    if content:
                        new_content = content.replace(f"{{{img_item['file']}}}", img_tag)
                        if new_content != content:
                            self._save_txt(txt_path, new_content)

        # 上傳 DS_BOX 各筆
        ds_box_meta = article["ds_box"]["meta"] or []
        total = len(ds_box_meta)
        for i, box_item in enumerate(ds_box_meta, 1):
            logger.info(f"    ({i}/{total}) {box_item['file']}")

            if box_item.get("cms_id"):
                logger.debug(f"已跳過（cms_id={box_item['cms_id']}）")
                continue

            txt_path = os.path.join(article["ds_box"]["dir"], box_item["file"])
            content = self._read_txt(txt_path) or ""
            content_html = self._txt_to_html(content)

            cms_id = self.browser.upload_box(
                title=box_item.get("title", ""),
                content_html=content_html,
                category=box_item.get("category", ""),
            )

            box_item["cms_id"] = cms_id
            self._save_meta(article["ds_box"]["dir"], article["ds_box"]["meta"])

            article["article_txt"] = self._replace_placeholder(
                article["article_txt"], box_item["file"], cms_id, prefix="DS_BOX"
            )
            logger.debug(f"替換佔位符 {{{box_item['file']}}} → {{DS_BOX_{cms_id}}}")
            self._save_txt(os.path.join(article["path"], "article.txt"), article["article_txt"])

    # ── 最後一步：建立文章 ───────────────────────────────────

    def _create_article(self, article: dict, total_steps: int):
        logger.info(f"  步驟 {total_steps}/{total_steps} - 建立文章")
        field = article.get("field") or {}
        content_html = self._txt_to_html(article.get("article_txt") or "")
        channel = self.browser.config.get("default_channel", "財經")

        # 解析 image_index → cms_guid
        gallery_guid = None
        image_index = field.get("image_index", "")
        if image_index:
            ds_img_meta = article.get("ds_img", {}).get("meta") or []
            matched = next((m for m in ds_img_meta if m.get("file") == image_index), None)
            if matched:
                gallery_guid = matched.get("cms_guid")

        guid = self.browser.create_article(
            field=field,
            issue=self.issue,
            content_html=content_html,
            channel=channel,
            gallery_guid=gallery_guid,
        )

        edit_url = self.browser._url(f"CTMagazine/Edit/{guid}")
        title = field.get("Title", "")
        self.csv_rows.append({"標題": title, "編輯網址": edit_url})
        logger.debug(f"CSV 記錄：{title} → {edit_url}")

    # ── 工具方法 ─────────────────────────────────────────────

    def _replace_placeholder(self, content: str, filename: str, cms_id: str, prefix: str = "DS_IMG") -> str:
        """把 {filename} 替換成 CMS 格式的 ID。"""
        return content.replace(f"{{{filename}}}", f"{{{prefix}_{cms_id}}}")

    def _save_meta(self, dir_path: str, meta: list):
        """將 meta 寫回對應資料夾的 meta.json。"""
        path = os.path.join(dir_path, "meta.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    def _read_txt(self, path: str) -> str | None:
        if not os.path.exists(path):
            return None
        for enc in ["utf-8-sig", "utf-8", "cp950"]:
            try:
                with open(path, encoding=enc) as f:
                    return f.read()
            except Exception:
                continue
        return None

    def _save_txt(self, path: str, content: str):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _txt_to_html(self, txt: str) -> str:
        """將 txt 內容轉換為 HTML。
        ## 標題 → <h2>標題</h2>
        連續以 > 開頭的行 → 合併為一個抽言 <blockquote class="blockquote">，行間以 <br> 連接
        一般行 → <p>行內容</p>（每行各自一個 <p>，空白行忽略）
        已替換的 <img> 標籤直接保留為 <p><img ...></p>
        """
        lines = txt.splitlines()
        html_parts = []
        quote_buffer = []

        def flush_quote():
            if quote_buffer:
                html_parts.append(f'<blockquote class="blockquote">{"<br>".join(quote_buffer)}</blockquote>')
                quote_buffer.clear()

        for line in lines:
            stripped = line.strip().strip("\r")
            if not stripped:
                flush_quote()
                continue
            if stripped.startswith(">"):
                quote_buffer.append(stripped[1:].strip())
                continue
            flush_quote()
            if stripped.startswith("##"):
                heading = stripped.lstrip('#').strip()
                inner = "<br>".join(part.strip() for part in heading.split("|"))
                html_parts.append(f"<h2>{inner}</h2>")
            elif stripped.startswith("<img"):
                html_parts.append(f"<p>{stripped}</p>")
            else:
                html_parts.append(f"<p>{stripped}</p>")

        flush_quote()
        return "\n".join(html_parts)

    # ── 結尾清理 ─────────────────────────────────────────────

    def _finalize(self, debug: bool = False):
        """全部完成後，移動 ZIP、輸出 CSV 並清理。debug 模式下保留 temp/。"""
        os.makedirs(DONE_DIR, exist_ok=True)

        if self.zip_path and os.path.exists(self.zip_path):
            shutil.move(self.zip_path, os.path.join(DONE_DIR, os.path.basename(self.zip_path)))
            logger.debug(f"ZIP 已移至 done/")

        # 輸出 CSV
        if self.csv_rows:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join(DONE_DIR, f"{ts}_{self.issue}.csv")
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["標題", "編輯網址"])
                writer.writeheader()
                writer.writerows(self.csv_rows)
            logger.info(f"已輸出報表：{csv_path}")

        if debug:
            logger.debug("Debug 模式：temp/ 保留")
        else:
            if os.path.exists(TEMP_DIR):
                shutil.rmtree(TEMP_DIR)
            logger.debug("temp/ 清理完成")

        self.tracker.finish()
