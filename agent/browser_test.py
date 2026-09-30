from playwright.sync_api import sync_playwright


def main():
    print("=" * 50)
    print("RAJESH AI - BROWSER TEST")
    print("=" * 50)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page()
        page.goto("https://example.com", wait_until="domcontentloaded")

        print("Browser        : OK")
        print("Page title     :", page.title())
        print("URL            :", page.url)

        browser.close()

    print("Browser test   : PASSED")
    print("=" * 50)


if __name__ == "__main__":
    main()