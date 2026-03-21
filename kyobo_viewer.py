"""
교보문고 베스트셀러 순위 변동 뷰어
=====================================
사용법:
  python kyobo_viewer.py              # 최신 순위 보기
  python kyobo_viewer.py --history    # 특정 책의 순위 변동 추적
  python kyobo_viewer.py --compare    # 두 시점 비교
"""

import csv
import argparse
from pathlib import Path
from collections import defaultdict

DATA_FILE = "kyobo_bestseller.csv"


def load_all() -> list[dict]:
    path = Path(DATA_FILE)
    if not path.exists():
        print(f"❌ {DATA_FILE} 파일이 없어요. 먼저 kyobo_collector.py 를 실행하세요.")
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def get_snapshots(rows: list[dict]) -> dict[str, list[dict]]:
    """수집시각별로 그룹핑"""
    snap = defaultdict(list)
    for r in rows:
        snap[r["수집시각"]].append(r)
    return dict(snap)


def show_latest(rows):
    """최신 수집 결과 출력"""
    snaps = get_snapshots(rows)
    latest_time = max(snaps.keys())
    books = sorted(snaps[latest_time], key=lambda x: int(x["순위"]) if x["순위"].isdigit() else 99)

    print(f"\n📚 교보문고 실시간 베스트  [{latest_time}]")
    print(f"{'순위':>4}  {'변동':>5}  {'제목':<42}  {'저자':<20}  {'출판사'}")
    print("─" * 100)

    for b in books:
        change = b.get("순위변동", "-")
        if change.startswith("↑"):
            change_str = f"🟢{change}"
        elif change.startswith("↓"):
            change_str = f"🔴{change}"
        elif change == "NEW":
            change_str = "✨NEW"
        else:
            change_str = f"  {change} "

        print(f"{b['순위']:>4}  {change_str:<6}  {b['제목'][:40]:<42}  {b['저자'][:18]:<20}  {b['출판사'][:15]}")

    print(f"\n총 {len(books)}권 | 수집 횟수: {len(snaps)}회")


def show_history(rows):
    """특정 책의 순위 변동 추적"""
    keyword = input("\n🔍 추적할 책 제목 (일부만 입력 가능): ").strip()
    if not keyword:
        return

    matched = defaultdict(dict)  # 제목 → {시각: 순위}
    for r in rows:
        if keyword in r["제목"]:
            matched[r["제목"]][r["수집시각"]] = r["순위"]

    if not matched:
        print(f"  '{keyword}'를 포함하는 책이 없어요.")
        return

    all_times = sorted(set(r["수집시각"] for r in rows))

    for title, history in matched.items():
        print(f"\n📖 {title}")
        print(f"{'시각':<18}  {'순위':>4}")
        print("─" * 30)
        prev = None
        for t in all_times:
            rank = history.get(t, "-")
            if rank == "-":
                change = ""
            elif prev is None or prev == "-":
                change = " (NEW)"
            else:
                try:
                    diff = int(prev) - int(rank)
                    change = f" (↑{diff})" if diff > 0 else (f" (↓{abs(diff)})" if diff < 0 else " (-)")
                except:
                    change = ""
            print(f"  {t:<18}  {rank:>4}{change}")
            if rank != "-":
                prev = rank


def show_compare(rows):
    """두 시점 순위 비교"""
    snaps = get_snapshots(rows)
    times = sorted(snaps.keys())

    if len(times) < 2:
        print("  비교하려면 수집 데이터가 2개 이상 있어야 해요.")
        return

    print("\n수집 시각 목록:")
    for i, t in enumerate(times):
        print(f"  [{i}] {t}")

    try:
        a = int(input("첫 번째 시각 번호: "))
        b = int(input("두 번째 시각 번호: "))
        time_a, time_b = times[a], times[b]
    except (ValueError, IndexError):
        print("잘못된 입력이에요.")
        return

    snap_a = {r["제목"]: int(r["순위"]) for r in snaps[time_a] if r["순위"].isdigit()}
    snap_b = {r["제목"]: int(r["순위"]) for r in snaps[time_b] if r["순위"].isdigit()}
    all_titles = sorted(set(snap_a) | set(snap_b))

    print(f"\n{'제목':<45}  {time_a[:16]:>16}  {time_b[:16]:>16}  변동")
    print("─" * 95)

    for title in sorted(all_titles, key=lambda t: snap_b.get(t, 99)):
        r_a = snap_a.get(title, "-")
        r_b = snap_b.get(title, "-")
        if r_a == "-":
            change = "✨NEW"
        elif r_b == "-":
            change = "❌OUT"
        else:
            diff = r_a - r_b
            change = f"🟢↑{diff}" if diff > 0 else (f"🔴↓{abs(diff)}" if diff < 0 else "  -")
        print(f"  {title[:43]:<45}  {str(r_a):>16}  {str(r_b):>16}  {change}")


def show_stats(rows):
    """간단한 통계"""
    snaps = get_snapshots(rows)
    title_counts = defaultdict(int)
    title_best = defaultdict(lambda: 99)

    for snap in snaps.values():
        for b in snap:
            t = b["제목"]
            title_counts[t] += 1
            if b["순위"].isdigit():
                title_best[t] = min(title_best[t], int(b["순위"]))

    # 가장 오래 베스트에 머문 책 TOP 10
    top = sorted(title_counts.items(), key=lambda x: -x[1])[:10]
    print(f"\n🏆 베스트셀러 최장 기간 차트 (총 {len(snaps)}회 수집 기준)")
    print(f"{'제목':<45}  {'출현횟수':>8}  {'최고순위':>8}")
    print("─" * 70)
    for title, cnt in top:
        best = title_best.get(title, "-")
        print(f"  {title[:43]:<45}  {cnt:>8}회  {str(best):>7}위")


def main():
    rows = load_all()
    if not rows:
        return

    parser = argparse.ArgumentParser(description="교보문고 순위 변동 뷰어")
    parser.add_argument("--history", action="store_true", help="책별 순위 변동 추적")
    parser.add_argument("--compare", action="store_true", help="두 시점 비교")
    parser.add_argument("--stats", action="store_true", help="통계 보기")
    args = parser.parse_args()

    if args.history:
        show_history(rows)
    elif args.compare:
        show_compare(rows)
    elif args.stats:
        show_stats(rows)
    else:
        show_latest(rows)


if __name__ == "__main__":
    main()
