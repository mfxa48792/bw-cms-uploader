import json
import os

PROGRESS_PATH = "progress.json"


class ProgressTracker:
    def __init__(self, total: int):
        self.total = total
        self.current_article = 0
        self.current_step = 0
        self.articles: dict = {}

    def check_resume(self):
        """若有 progress.json，詢問是否續跑。"""
        if not os.path.exists(PROGRESS_PATH):
            return

        with open(PROGRESS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        art = data.get("current_article", 0)
        step = data.get("current_step", 0)
        print(f"偵測到上次未完成的進度：第 {art + 1} 篇 / 第 {step + 1} 步")
        ans = input("是否從上次繼續？(y/n)：").strip().lower()

        if ans == "y":
            self.current_article = art
            self.current_step = step
            self.articles = data.get("articles", {})
            print(f"從第 {art + 1} 篇第 {step + 1} 步繼續\n")
        else:
            self.reset()

    def save(self):
        data = {
            "total": self.total,
            "current_article": self.current_article,
            "current_step": self.current_step,
            "articles": self.articles,
        }
        with open(PROGRESS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def mark_step(self, article_idx: int, step: int):
        self.current_article = article_idx
        self.current_step = step
        self.articles[str(article_idx)] = f"step_{step}_done"
        self.save()

    def mark_article_done(self, article_idx: int):
        self.articles[str(article_idx)] = "done"
        self.current_step = 0
        self.save()

    def finish(self):
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)

    def reset(self):
        self.current_article = 0
        self.current_step = 0
        self.articles = {}
        if os.path.exists(PROGRESS_PATH):
            os.remove(PROGRESS_PATH)
