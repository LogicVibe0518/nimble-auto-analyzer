"""Temporary script: scrape all 3 demo URLs and save to scraped_data.json"""
import json
from utils.scraper import scrape_url

URLS = {
    "client": "https://hotelholidayhill.co.in/",
    "competitor_1": "https://www.lemontreehotels.com/lemon-tree-hotel/mcleodganj/hotel-mcleodganj",
    "competitor_2": "https://www.leisurehotels.co.in/mcleodganj/belvedere-himalayan-retreat/",
}

results = {}
for label, url in URLS.items():
    print(f"\nScraping {label}: {url}")
    result = scrape_url(url)
    print(f"  Success: {result.success}")
    if result.success:
        print(f"  Title: {result.title}")
        print(f"  Word count: {result.word_count}")
        print(f"  Body sample (first 200 chars): {(result.body_text or '')[:200]}")
    else:
        print(f"  Error: {result.error_message}")
    results[label] = result.model_dump()

with open("scraped_data.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n✅ Saved to scraped_data.json")