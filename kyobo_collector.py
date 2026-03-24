"""
교보문고 / 알라딘 / 예스24 실시간 베스트셀러 수집기
"""

import csv
import json
import time
import argparse
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("playwright가 없어요: pip3 install playwright")
    exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("beautifulsoup4가 없어요: pip3 install beautifulsoup4")
    exit(1)

KST = timezone(timedelta(hours=9))
HISTORY_FILE = "history.json"
STORES = ["kyobo", "aladin", "yes24"]
FIELDNAMES = ["수집시각", "순위", "제목", "저자", "출판사", "링크", "이전순위", "순위변동"]


def fetch_html(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ))
        page = context.new_page()
        page.goto(url, timeout=30000)
        page.wait_for_timeout(4000)
        html = page.content()
        browser.close()
    return html


def parse_kyobo(html, now):
    soup = BeautifulSoup(html, "html.parser")
    ols = [ol for ol in soup.find_all("ol") if "grid" in (ol.get("class") or [])]
    books = []
    for ol in ols:
        for item in ol.find_all("li", recursive=False):
            title_a = item.find("a", class_=lambda c: c and "prod_link" in c and "line-clamp-2" in c)
            if not title_a:
                continue
            link = title_a.get("href", "")
            for span in title_a.find_all("span"):
                span.decompose()
            title = title_a.get_text(strip=True)
            rank_div = item.find("div", class_=lambda c: c and "block" in c and any("min-w" in x for x in c))
            rank_raw = rank_div.get_text(strip=True) if rank_div else str(len(books)+1)
            rank = "".join(filter(str.isdigit, rank_raw)) or str(len(books)+1)
            info_div = item.find("div", class_=lambda c: c and "line-clamp-2" in c and "break-all" in c)
            author = publisher = ""
            if info_div:
                date_span = info_div.find("span", class_="date")
                date_str = date_span.get_text(strip=True) if date_span else ""
                text = info_div.get_text(strip=True).replace(date_str, "").strip().rstrip(".")
                parts = [p.strip() for p in text.split(".") if p.strip()]
                author = parts[0] if parts else ""
                publisher = parts[1] if len(parts) > 1 else ""
            books.append({"수집시각": now, "순위": rank, "제목": title,
                          "저자": author, "출판사": publisher, "링크": link,
                          "이전순위": "", "순위변동": ""})
            if len(books) >= 100:
                break
        if len(books) >= 100:
            break
    return books


def parse_aladin_html(html, now, offset=0):
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for div in soup.find_all("div", class_="ss_book_list"):
        title_a = div.find("a", class_="bo3")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        link = title_a.get("href", "")
        li_items = div.find_all("li")
        author = publisher = ""
        for li in li_items:
            text = li.get_text(strip=True)
            if "지은이" in text or "옮긴이" in text or "저" in text:
                a_tags = li.find_all("a")
                names = [a.get_text(strip=True) for a in a_tags if a.get_text(strip=True)]
                if names:
                    publisher = names[-1]
                    author = ", ".join(names[:-1])
                break
        rank = str(offset + len(books) + 1)
        books.append({"수집시각": now, "순위": rank, "제목": title,
                      "저자": author, "출판사": publisher, "링크": link,
                      "이전순위": "", "순위변동": ""})
    return books


def scrape_aladin(now):
    books = []
    for page in [1, 2]:
        url = f"https://www.aladin.co.kr/shop/common/wbest.aspx?BestType=NowBest&BranchType=1&CID=0&page={page}&cnt=100&SortOrder=1"
        html = fetch_html(url)
        page_books = parse_aladin_html(html, now, offset=len(books))
        books.extend(page_books)
        if len(books) >= 100:
            break
    return books[:100]


def parse_yes24(html, now):
    soup = BeautifulSoup(html, "html.parser")
    books = []
    seen = set()
    for li in soup.find_all("li"):
        item_div = li.find("div", class_="itemUnit")
        if not item_div:
            continue
        rank_tag = item_div.find("em", class_="ico rank")
        rank = rank_tag.get_text(strip=True) if rank_tag else str(len(books)+1)
        title_a = item_div.find("a", class_="gd_name")
        if not title_a:
            continue
        title = title_a.get_text(strip=True)
        if title in seen:
            continue
        seen.add(title)
        link = title_a.get("href", "")
        if link and not link.startswith("http"):
            link = "https://www.yes24.com" + link
        auth_span = item_div.find("span", class_="info_auth")
        author = auth_span.get_text(strip=True) if auth_span else ""
        author = re.sub(r"(저|역|지은이|옮긴이)", "", author).strip().strip("/")
        pub_span = item_div.find("span", class_="info_pub")
        publisher = pub_span.get_text(strip=True) if pub_span else ""
        books.append({"수집시각": now, "순위": rank, "제목": title,
                      "저자": author, "출판사": publisher, "링크": link,
                      "이전순위": "", "순위변동": ""})
        if len(books) >= 100:
            break
    return books


def scrape_all(now):
    results = {}
    print("교보문고 수집 중...")
    try:
        html = fetch_html("https://store.kyobobook.co.kr/bestseller/realtime")
        results["kyobo"] = parse_kyobo(html, now)
        print(f"  교보문고 {len(results['kyobo'])}권")
    except Exception as e:
        print(f"  교보문고 실패: {e}")
        results["kyobo"] = []
    print("알라딘 수집 중...")
    try:
        results["aladin"] = scrape_aladin(now)
        print(f"  알라딘 {len(results['aladin'])}권")
    except Exception as e:
        print(f"  알라딘 실패: {e}")
        results["aladin"] = []
    print("예스24 수집 중...")
    try:
        html = fetch_html("https://www.yes24.com/product/category/realtimebestseller?categoryNumber=001")
        results["yes24"] = parse_yes24(html, now)
        print(f"  예스24 {len(results['yes24'])}권")
    except Exception as e:
        print(f"  예스24 실패: {e}")
        results["yes24"] = []
    return results


def load_last_snapshot(store):
    path = Path(HISTORY_FILE)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        history = json.load(f)
    if not history:
        return {}
    last_entry = history[-1]
    data = last_entry.get("데이터", {})
    if not isinstance(data, dict):
        return {}
    store_data = data.get(store, [])
    return {row["제목"]: row["순위"] for row in store_data if isinstance(row, dict)}


def calc_change(current, previous):
    if not previous:
        return "NEW"
    try:
        diff = int(previous) - int(current)
        if diff > 0:
            return f"up{diff}"
        elif diff < 0:
            return f"down{abs(diff)}"
        else:
            return "-"
    except ValueError:
        return "-"


def save_csv(store, books):
    path = Path(f"{store}_bestseller.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(books)
    print(f"  {path} 저장 ({len(books)}권)")


def save_history(all_books, now):
    path = Path(HISTORY_FILE)
    history = []
    if path.exists():
        with open(path, encoding="utf-8") as f:
            try:
                history = json.load(f)
                history = [h for h in history if isinstance(h.get("데이터", {}), dict)]
            except Exception:
                history = []
    history.append({"수집시각": now, "데이터": all_books})
    history = history[-30:]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  history.json 저장 (총 {len(history)}회)")


def collect_once(is_scheduled=True):
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"\n{now} 수집 시작\n")
    all_books = scrape_all(now)
    for store in STORES:
        books = all_books.get(store, [])
        if not books:
            continue
        last = load_last_snapshot(store)
        for book in books:
            prev = last.get(book["제목"], "")
            book["이전순위"] = prev
            book["순위변동"] = calc_change(book["순위"], prev)
        save_csv(store, books)
    if is_scheduled:
        save_history(all_books, now)
        print("\n자동 수집 완료 - history.json 저장")
    else:
        print("\n수동 수집 완료 - history.json 미저장")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", type=int, default=0)
    parser.add_argument("--event", type=str, default="schedule")
    args = parser.parse_args()
    is_scheduled = (args.event == "schedule")
    if args.loop > 0:
        while True:
            collect_once(is_scheduled=True)
            time.sleep(args.loop * 60)
    else:
        collect_once(is_scheduled=is_scheduled)


if __name__ == "__main__":
    main()
