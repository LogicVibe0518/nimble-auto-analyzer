"""Manual source-capture helper retained from the original prototype.

Run explicitly with `python test_scraper.py`. Automated tests live in tests/.
"""
import json
from utils.safe_scraper import scrape_url_safe

URLS = {
    "client": "https://hotelholidayhill.co.in/",
    "competitor_1": "https://www.lemontreehotels.com/lemon-tree-hotel/mcleodganj/hotel-mcleodganj",
    "competitor_2": "https://www.leisurehotels.co.in/mcleodganj/belvedere-himalayan-retreat/",
}


def main():
    results = {}
    for label, url in URLS.items():
        result = scrape_url_safe(url)
        print(f"{label}: {result.word_count} words" if result.success else f"{label}: {result.error_message}")
        results[label] = result.model_dump()
    with open("scraped_data.json", "w", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)
    print("Saved to scraped_data.json")


if __name__ == "__main__":
    main()
