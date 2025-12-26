import logging
import re
import requests
import time
from bs4 import BeautifulSoup


class WebFetcher:
    def __init__(self):
        self.logger = self._setup_logging()

    def _setup_logging(self):
        """启用日志管理"""

        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def _clean_html(self, html):
        """HTML预处理：移除脚本、注释、样式，统一格式"""

        soup = BeautifulSoup(html, "html.parser")

        # 移除脚本、样式、注释
        for element in soup(["script", "style", "comment"]):
            element.decompose()

        # 获取处理后的HTML并压缩空白
        normalized_html = re.sub(r"\s+", " ", str(soup)).strip()

        return soup, normalized_html

    def _fetch_with_requests(self, url):
        """使用requests获取静态内容"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        return response.text

    def _fetch_with_playwright(self, url):
        """使用Playwright获取动态内容"""
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth.stealth import Stealth

            with sync_playwright() as p, p.chromium.launch(
                headless=True
            ) as browser, browser.new_context() as context, context.new_page() as page:
                Stealth().apply_stealth_sync(page)

                page.goto(url, wait_until="networkidle")
                page.wait_for_timeout(3000)

                return page.content()
        except ImportError:
            self.logger.error(
                "请安装playwright: pip install playwright && playwright install"
            )
            return None
        except Exception as e:
            self.logger.error(f"Playwright获取内容失败: {e}")
            return None

    def fetch_content(self, url, use_js=False, css_selector=None):
        """获取网页内容"""
        try:
            if use_js:
                raw_html = self._fetch_with_playwright(url)
            else:
                raw_html = self._fetch_with_requests(url)

            extracted_html = None
            if css_selector:
                soup, normalized_html = self._clean_html(raw_html)
                elements = soup.select(css_selector)
                if elements:
                    extracted_html = "\n".join(
                        [element.get_text(strip=True) for element in elements]
                    )

                return {
                    "raw_html": raw_html,
                    "normalized_html": normalized_html,
                    "extracted_html": extracted_html,
                    "timestamp": time.time(),
                }

            return {
                "raw_html": raw_html,
                "timestamp": time.time(),
            }
        except Exception as e:
            self.logger.error(f"获取 {url} 内容失败: {e}")
            return None


if __name__ == "__main__":
    fetcher = WebFetcher()
    result = fetcher.fetch_content(
        "https://wallstreetcn.com/articles/3762000", use_js=True
    )
    print(result)
