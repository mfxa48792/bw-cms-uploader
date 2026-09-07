import getpass
import json
import os
from playwright.sync_api import sync_playwright, Page, Browser as PWBrowser
from src.logger import logger

CONFIG_PATH = "config.json"


def _summary_to_html(summary: str) -> str:
    """Summary/Lead/ExtendedReading 欄位：以 \\n 切割，每行一個 <p>；行內以 | 切段，段間以 <br> 連接；**文字** → <b>文字</b>。"""
    import re
    lines = [line.strip() for line in summary.splitlines() if line.strip()]
    result = []
    for line in lines:
        segments = [re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', seg.strip()) for seg in line.split("|")]
        result.append(f"<p>{'<br>'.join(segments)}</p>")
    return "\n".join(result)


class Browser:
    def __init__(self, config: dict):
        self.config = config
        self._playwright = None
        self._browser: PWBrowser = None
        self.page: Page = None

    def _url(self, path: str) -> str:
        base = self.config["url"].rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    def _goto(self, path: str):
        url = self._url(path)
        logger.debug(f"goto {url}")
        self.page.goto(url, wait_until="domcontentloaded")

    def _click(self, selector: str):
        logger.debug(f"click {selector}")
        self.page.click(selector)

    def _fill(self, selector: str, value: str):
        logger.debug(f"fill {selector} = {value!r}")
        self.page.fill(selector, value)

    def _select(self, selector: str, **kwargs):
        label = kwargs.get("label", kwargs.get("value", ""))
        logger.debug(f"select {selector} = {label!r}")
        try:
            self.page.select_option(selector, **kwargs, timeout=3000)
        except Exception:
            self._select_manual(selector, reason=f"找不到選項 {label!r}")

    def _select_manual(self, selector: str, reason: str = "請選擇"):
        options = self.page.eval_on_selector_all(
            f"{selector} option",
            "els => els.map(e => e.textContent.trim()).filter(t => t)"
        )
        if not options:
            raise Exception(f"{selector} 沒有可選項目")
        print(f"\n{reason}，請手動選擇：")
        for i, opt in enumerate(options, 1):
            print(f"  {i}. {opt}")
        while True:
            try:
                idx = int(input("輸入編號：")) - 1
                if 0 <= idx < len(options):
                    self.page.select_option(selector, label=options[idx])
                    logger.debug(f"手動選擇 {selector} = {options[idx]!r}")
                    return options[idx]
            except ValueError:
                pass
            print("請輸入有效的編號")

    def _radio(self, name: str, label: str):
        logger.debug(f"radio {name} = {label!r}")

    def login(self):
        self._playwright = sync_playwright().start()
        is_debug = self.config.get("debug", 1) == 1
        self._browser = self._playwright.chromium.launch(headless=not is_debug)
        self.page = self._browser.new_page(ignore_https_errors=True)

        logger.info("正在開啟上稿系統...")
        logger.debug(f"goto {self.config['url']}")
        self.page.goto(self.config["url"], wait_until="domcontentloaded")

        while True:
            self._fill_login_form()
            self.page.wait_for_function(
                "() => window.location.href.includes('/Home/Index') || "
                "document.querySelector('.alertify-log') !== null",
                timeout=15000,
            )

            if "/Home/Index" in self.page.url:
                logger.info("登入成功\n")
                return
            else:
                logger.info("[錯誤] 登入失敗，帳號或密碼不正確。\n")
                self._prompt_new_credentials()
                logger.debug(f"goto {self.config['url']}")
                self.page.goto(self.config["url"], wait_until="domcontentloaded")

    def _fill_login_form(self):
        self.page.wait_for_selector("input[name='UserCode']")
        logger.debug(f"fill UserCode = {self.config['username']!r}")
        self.page.fill("input[name='UserCode']", self.config["username"])
        logger.debug("fill Password = ********")
        self.page.fill("input[name='Password']", self.config["password"])
        logger.debug("press Enter")
        self.page.keyboard.press("Enter")

    def _prompt_new_credentials(self):
        logger.info("請重新輸入帳號密碼：")
        self.config["username"] = input("帳號：").strip()
        self.config["password"] = getpass.getpass("密碼：").strip()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)
        logger.info("已更新設定\n")

    def verify_magazine(self, issue: str) -> bool:
        MAGAZINE_OPTIONS = {
            "1": "商業周刊",
            "2": "alive",
        }
        print("請選擇刊別：")
        for k, v in MAGAZINE_OPTIONS.items():
            print(f"  {k}. {v}")
        while True:
            choice = input("輸入編號：").strip()
            if choice in MAGAZINE_OPTIONS:
                break
            print("請輸入 1 或 2")
        magazine_label = MAGAZINE_OPTIONS[choice]

        logger.info(f"驗證期數 {issue}（{magazine_label}）...")
        self._goto("Magazine/Index")
        self.page.wait_for_selector("#SearchVol")
        self._fill("#SearchVol", issue)
        self._select("#MagazineCategoryId", label=magazine_label)
        self._click("#search_btn")
        self.page.wait_for_selector("p.count")

        count_text = self.page.locator("p.count i").first.inner_text().strip()
        logger.debug(f"搜尋結果筆數：{count_text}")

        if count_text == "0":
            logger.info(f"[錯誤] 查無期數 {issue}，請至 CMS 雜誌管理新增後再執行。\n")
            return False

        logger.info(f"期數 {issue} 驗證成功\n")
        return True

    def get_gallery_credentials(self) -> tuple:
        """前往 Gallery/Index，取得 site_id 和 cookies 供並行上傳使用。"""
        self._goto("Gallery/Index")
        site_id = self.page.locator("#NowWebSiteId").input_value()
        cookies = {c["name"]: c["value"] for c in self.page.context.cookies()}
        logger.debug(f"NowWebSiteId = {site_id}")
        return site_id, cookies

    def post_image_file(self, img_path: str, site_id: str, cookies: dict) -> str:
        """
        只做 POST 上傳，回傳 ImgName。可並行呼叫。
        """
        import requests
        import uuid
        import urllib3
        urllib3.disable_warnings()

        filename = os.path.basename(img_path)
        ext = os.path.splitext(img_path)[1].lower()
        guid_filename = str(uuid.uuid4()) + ext
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

        logger.debug(f"POST Gallery/Create filename={guid_filename} ({filename})")
        with open(img_path, "rb") as f:
            resp = requests.post(
                self._url("Gallery/Create"),
                cookies=cookies,
                files={"FileUpload": (guid_filename, f, mime)},
                data={"NowWebSiteId": site_id},
                verify=False,
            )

        resp_data = resp.json()
        logger.debug(f"Gallery/Create 回應：{resp_data}")

        if not resp_data.get("isUploaded"):
            raise Exception(f"圖片上傳失敗：{resp_data.get('ErrorLog')} ({filename})")

        return resp_data["ImgName"]

    def fill_image_row(self, img_name: str, title: str, desc: str, author_label: str, author_value: str) -> tuple:
        """
        在 Gallery 頁面找到 img_name 對應的列（含翻頁），填入資料後儲存，回傳 (cms_id, img_url)。
        """
        row = self._find_gallery_row(img_name)

        if title:
            logger.debug(f"fill .Title = {title!r}")
            row.locator(".Title").fill(title)
        if desc:
            logger.debug(f"fill .Description = {desc!r}")
            row.locator(".Description").fill(desc)
        if author_label:
            logger.debug(f"select .AuthorType = {author_label!r}")
            row.locator(".AuthorType").select_option(label=author_label.strip())
        if author_value:
            logger.debug(f"fill .Author = {author_value!r}")
            row.locator(".Author").fill(author_value)

        cms_id = row.locator(".SourceId").input_value()
        cms_guid = row.locator("a.del_btn").get_attribute("id")
        img_url = row.locator("img").get_attribute("src")

        logger.debug(f"click .btn_Store")
        self.page.locator("a.icon_btn.btn_Store").click()
        logger.debug(f"圖片儲存完成 SourceId={cms_id} GUID={cms_guid} ImgName={img_name}")

        return cms_id, cms_guid, img_url

    def _find_gallery_row(self, img_name: str):
        """在 Gallery/Index 翻頁尋找 img_name 對應的列。"""
        while True:
            rows = self.page.locator(f'.box.Datarow:has(img[src$="{img_name}"])')
            if rows.count() > 0:
                return rows.first

            # 嘗試翻下一頁
            next_btn = self.page.locator("a.arrow_btn.right")
            if next_btn.is_disabled() or not next_btn.is_visible():
                raise Exception(f"找不到圖片列：{img_name}")

            logger.debug(f"翻頁尋找 {img_name}")
            next_btn.click()
            self.page.wait_for_load_state("domcontentloaded")

    def upload_box(self, title: str, content_html: str, category: str = "") -> str:
        logger.debug(f"上傳BOX：{title!r}")
        self._goto("Box/Index")
        self._click("#btn_Add")
        self.page.wait_for_load_state("domcontentloaded")

        guid = self.page.url.rstrip("/").split("/")[-1]
        logger.debug(f"BOX GUID = {guid}")

        self._fill("#BoxName", title)
        if category:
            try:
                self._select("#CSSTypeId", label=category)
            except Exception:
                logger.debug(f"CSSTypeId 找不到對應選項：{category!r}，略過")
        logger.debug(f"evaluate Content (長度 {len(content_html)})")
        self.page.evaluate(f'document.getElementById("Content").value = {json.dumps(content_html)}')

        self._click("a.submit_btn.gray")
        self.page.wait_for_load_state("domcontentloaded")

        self._goto(f"Box/Edit/{guid}")
        cms_id = self.page.locator(".row:has(label[for='SourceId'])").inner_text()
        cms_id = cms_id.replace("序號代碼", "").strip()
        logger.debug(f"BOX 儲存完成 SourceId={cms_id}")

        return cms_id

    def create_article(self, field: dict, issue: str, content_html: str, channel: str, gallery_guid: str = None) -> str:
        logger.debug(f"建立文章：{field.get('Title', '')!r}")
        self._goto("CTMagazine/Index")
        self._click("#btn_Add")
        self.page.wait_for_load_state("domcontentloaded")

        guid = self.page.url.rstrip("/").split("/")[-1]
        logger.debug(f"文章 GUID = {guid}")

        magazine_main = field.get("MagazineMainCategoryId", "")
        options = self.page.eval_on_selector_all(
            "#MagazineMainCategoryId option",
            "els => els.map(e => e.textContent.trim())"
        )
        logger.debug(f"MagazineMainCategoryId options: {options}")
        matched = next((o for o in options if o.lower() == magazine_main.lower()), magazine_main)
        self._select("#MagazineMainCategoryId", label=matched)
        self.page.wait_for_function("() => document.querySelector('#MagazineId') && document.querySelector('#MagazineId').options.length > 1")
        self.page.wait_for_function("() => document.querySelector('#MagazineCategory_0') && document.querySelector('#MagazineCategory_0').options.length > 1")

        self._select("#MagazineId", label=issue)
        self._fill("#ArticleNo_Page", field.get("ArticleNo_Page") or "000")

        has_sub = False
        category_1 = field.get("MagazineCategory_1", "")
        category_0 = field.get("MagazineCategory_0", "")

        if not category_1 and not category_0:
            self._select_manual("#MagazineCategory_0", reason="欄目未填")
        else:
            if category_1:
                self._select("#MagazineCategory_0", label=category_1)
                try:
                    self.page.wait_for_function(
                        "() => document.querySelector('#MagazineCategory_1') && document.querySelector('#MagazineCategory_1').options.length > 1",
                        timeout=5000,
                    )
                    has_sub = True
                except Exception:
                    has_sub = False
                    logger.debug("無子階層，略過二級分類")

            if category_0 and (has_sub or not category_1):
                self._select("#MagazineCategory_0", label=category_0)

        for field_id in ["Title", "SubTitle", "Producer", "Author", "Classfieder",
                         "Interviewer", "Researcher", "Translator"]:
            val = field.get(field_id, "")
            if val:
                self._fill(f"#{field_id}", val)

        channel_label = field.get("ChannelId", channel)
        self._radio("ChannelId", channel_label)
        radio = self.page.locator("label").filter(
            has=self.page.locator(f"span:text('{channel_label}')")
        ).locator("input[name='ChannelId']").first
        if not radio.is_checked():
            radio.check()

        for field_key, elem_id in [("Summary", "Summary"), ("Lead", "Description"), ("ExtendedReading", "ExtendContent")]:
            html = _summary_to_html(field.get(field_key, ""))
            if html:
                logger.debug(f"evaluate {elem_id} (長度 {len(html)})")
                self.page.evaluate(f'document.getElementById("{elem_id}").value = {json.dumps(html)}')

        if gallery_guid:
            logger.debug(f"set GalleryId = {gallery_guid}")
            self.page.locator("input[name='HasImgGroup'][value='R']").check()
            self.page.evaluate(f'''
                (function() {{
                    var el = document.getElementById("GalleryId");
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    setter.call(el, {json.dumps(gallery_guid)});
                    var overlay = document.getElementById("div_RelateGallery");
                    if (overlay) overlay.style.display = "none";
                }})();
            ''')
            logger.debug(f"GalleryId 驗證：{self.page.evaluate('document.getElementById(\"GalleryId\").value')!r}")

        logger.debug(f"evaluate Content (長度 {len(content_html)})")
        self.page.evaluate(f'document.getElementById("Content").value = {json.dumps(content_html)}')

        logger.debug("click submit_btn")
        self.page.locator("a.submit_btn.gray").click(timeout=120000)
        self.page.wait_for_load_state("domcontentloaded", timeout=120000)

        self._goto(f"CTMagazine/Edit/{guid}")
        cms_id = self.page.locator(".row:has(label:text('序號代碼'))").inner_text()
        cms_id = cms_id.replace("序號代碼", "").strip()
        logger.debug(f"文章儲存完成 SourceId={cms_id} GUID={guid}")

        return guid

    def wait_for_ajax(self, selector: str, timeout: int = 10000):
        logger.debug(f"wait_for_selector {selector}")
        self.page.wait_for_selector(selector, timeout=timeout)

    def close(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
