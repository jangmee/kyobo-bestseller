"""
교보문고 실시간 베스트셀러 수집기
====================================
사용법:
  1. pip3 install playwright beautifulsoup4
  2. python3 -m playwright install chromium
  3. python3 kyobo_collector.py              # 한 번 수집
  4. python3 kyobo_collector.py --loop 60   # 60분마다 자동 수집
"""

import csv
import time
import argparse
from datetime import datetime
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ playwright가 없어요. 먼저 설치해 주세요:")
    print("   pip3 install playwright")
    print("   python3 -m playwright install chromium")
    exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("❌ beautifulsoup4가 없어요. 먼저 설치해 주세요:")
    print("   pip3 install beautifulsoup4")
    exit(1)

DATA_FILE = "kyobo_bestseller.csv"
FIELDNAMES = ["수집시각", "순위", "제목", "저자", "출판사", "정가", "이전순위", "순위변동"]


def scrape_realtime_best() -> list:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()
        print("🌐 교보문고 접속 중...")
        page.goto("https://store.kyobobook.co.kr/bestseller/realtime", timeout=30000)
        page.wait_for_timeout(4000)
        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, 'html.parser')
    ols = [ol for ol in soup.find_all('ol') if 'grid' in (ol.get('class') or [])]

    books = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for ol in ols:
        items = ol.find_all('li', recursive=False)
        for item in items:
            title_a = item.find('a', class_=lambda c: c and 'prod_link' in c and 'line-clamp-2' in c)
            if not title_a:
                continue
            for span in title_a.find_all('span'):
                span.decompose()
            title = title_a.get_text(strip=True)

            rank_div = item.find('div', class_=lambda c: c and 'block' in c and any('min-w' in x for x in c))
            rank_raw = rank_div.get_text(strip=True) if rank_div else str(len(books) + 1)
            rank = ''.join(filter(str.isdigit, rank_raw)) or str(len(books) + 1)

            info_div = item.find('div', class_=lambda c: c and 'line-clamp-2' in c and 'break-all' in c)
            author = publisher = ""
            if info_div:
                date_span = info_div.find('span', class_='date')
                date_str = date_span.get_text(strip=True) if date_span else ""
                text = info_div.get_text(strip=True).replace(date_str, "").strip().rstrip(".")
                parts = [p.strip() for p in text.split("·") if p.strip()]
                author = parts[0] if parts else ""
                publisher = parts[1] if len(parts) > 1 else ""

            price_span = item.find('span', class_=lambda c: c and 'inline-block' in c and 'fz-16' in c)
            price = price_span.get_text(strip=True) if price_span else ""

            books.append({
                "수집시각": now,
                "순위": rank,
                "제목": title,
                "저자": author,
                "출판사": publisher,
                "정가": price,
                "이전순위": "",
                "순위변동": "",
            })

    return books


def load_last_snapshot():
    path = Path(DATA_FILE)
    if not path.exists():
        return {}
    last_time = None
    last_snapshot = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            t = row.get("수집시각", "")
            if t != last_time:
                last_time = t
                last_snapshot = {}
            last_snapshot[row["제목"]] = row["순위"]
    return last_snapshot


def calc_change(current, previous):
    if not previous:
        return "NEW"
    try:
        diff = int(previous) - int(current)
        if diff > 0:
            return f"↑{diff}"
        elif diff < 0:
            return f"↓{abs(diff)}"
        else:
            return "-"
    except ValueError:
        return "-"


def save_to_csv(books):
    path = Path(DATA_FILE)
    is_new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if is_new:
            writer.writeheader()
        writer.writerows(books)
    print(f"💾 {DATA_FILE} 에 저장 완료 ({len(books)}권)")


def collect_once():
    last = load_last_snapshot()
    books = scrape_realtime_best()

    if not books:
        print("❌ 데이터를 가져오지 못했어요.")
        return

    for book in books:
        prev = last.get(book["제목"], "")
        book["이전순위"] = prev
        book["순위변동"] = calc_change(book["순위"], prev)

    save_to_csv(books)

    print(f"\n{'순위':>4}  {'변동':>5}  {'제목':<40}  {'저자'}")
    print("-" * 75)
    for b in books:
        print(f"{b['순위']:>4}  {b['순위변동']:>5}  {b['제목'][:38]:<40}  {b['저자'][:20]}")


def main():
    parser = argparse.ArgumentParser(description="교보문고 실시간 베스트 수집기")
    parser.add_argument("--loop", type=int, default=0,
                        help="자동 수집 간격(분). 0이면 한 번만 실행")
    args = parser.parse_args()

    if args.loop > 0:
        print(f"🔄 {args.loop}분마다 자동 수집 시작 (종료: Ctrl+C)")
        while True:
            print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')} 수집 시작")
            collect_once()
            print(f"  → {args.loop}분 후 다시 수집합니다...")
            time.sleep(args.loop * 60)
    else:
        collect_once()


if __name__ == "__main__":
    main()
