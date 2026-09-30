from playwright.sync_api import sync_playwright
from urllib.parse import quote
import time


def main():
    query = '"GenAI Engineer" jobs India'

    print("=" * 60)
    print("NEXPLY - BROWSER SEARCH DIAGNOSTIC")
    print("=" * 60)
    print(f"Query: {query}")
    print()
    print("A browser window will open.")
    print("Do not close it manually.")
    print()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page(
            viewport={"width": 1366, "height": 768}
        )

        url = "https://www.google.com/search?q=" + quote(query)

        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30000
        )

        time.sleep(5)

        print("Page title:", page.title())
        print("Current URL:", page.url)

        print()
        print("Visible page text:")
        print("-" * 60)

        text = page.locator("body").inner_text()

        print(text[:5000])

        print("-" * 60)
        print()
        print("Browser will remain open for 15 seconds.")

        time.sleep(15)

        browser.close()


if __name__ == "__main__":
    main()