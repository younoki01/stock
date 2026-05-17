from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def get_soup(url: str, timeout: int = 15000) -> BeautifulSoup:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        html = page.content()
        browser.close()
    return BeautifulSoup(html, "lxml")
