#!/usr/bin/env python3
"""
Валидатор затраченных токенов для эксперимента с вложенными оркестраторами.

Читает SQLite-базу OpenCode (~/.local/share/opencode/opencode.db), находит
сессии эксперимента по заголовку 'nest-exp-depth-N' и отметкам старта прогонов
(logs/experiment_starts.txt), строит дерево master -> субагенты через
session.parent_id и считает токены по уровням.

Вывод:
  - таблица токенов на каждую сессию (input, output, cache_read, reasoning)
  - агрегат по дереву каждой глубины
  - среднее по прогонам, ст. отклонение, медиана
  - оверхед относительно baseline (глубина 0): абсолютный и в процентах
  - соотношение "полезной работы" (лист дерева) к координации (оркестраторы)

Использование:
  python3 nest-exp/validate_tokens.py [--db PATH] [--all]
  По умолчанию показывает детально только последний прогон + сводку по всем.
  --all — показать все прогоны детально.
"""

import argparse
import json
import os
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import datetime

DEFAULT_DB = os.path.expanduser("~/.local/share/opencode/opencode.db")
HERE = os.path.dirname(__file__)
MARKER_FILE = os.path.join(HERE, "logs", "experiment_start_ts.txt")
STARTS_HISTORY = os.path.join(HERE, "logs", "experiment_starts.txt")
TITLES = {0: "nest-exp-depth-0", 1: "nest-exp-depth-1", 2: "nest-exp-depth-2", 3: "nest-exp-depth-3"}


def ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def load_starts() -> list[int]:
    """Все отметки старта прогонов (unix ms), по возрастанию."""
    starts: set[int] = set()
    if os.path.exists(STARTS_HISTORY):
        with open(STARTS_HISTORY) as f:
            for line in f:
                line = line.strip()
                if line.isdigit():
                    starts.add(int(line))
    if os.path.exists(MARKER_FILE):
        with open(MARKER_FILE) as f:
            v = f.read().strip()
            if v.isdigit():
                starts.add(int(v))
    return sorted(starts)


def load_sessions(db_path: str, start_ts: int) -> dict[str, dict]:
    """Все сессии, созданные после start_ts (фильтр по времени)."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT s.id, s.parent_id, s.title, s.agent, s.model, s.cost,
               s.tokens_input, s.tokens_output, s.tokens_reasoning,
               s.tokens_cache_read, s.tokens_cache_write,
               s.time_created, s.time_updated
        FROM session s
        WHERE s.time_created >= ?
        """,
        (start_ts,),
    ).fetchall()
    con.close()
    return {r["id"]: dict(r) for r in rows}


def build_trees(sessions: dict[str, dict]) -> list[dict]:
    """Деревья эксперимента. Возвращает список {root_id, root, depth, stats}."""
    by_parent: dict[str, list[str]] = defaultdict(list)
    for sid, s in sessions.items():
        if s["parent_id"] and s["parent_id"] in sessions:
            by_parent[s["parent_id"]].append(sid)

    for sid, s in sessions.items():
        s["children"] = by_parent.get(sid, [])

    trees = []
    for sid, s in sessions.items():
        title = s.get("title") or ""
        for depth, t in TITLES.items():
            if title == t:
                trees.append({"root_id": sid, "root": s, "depth": depth,
                              "stats": aggregate(sessions, sid)})
                break
    trees.sort(key=lambda t: (t["depth"], t["root"]["time_created"]))
    return trees


def aggregate(sessions: dict[str, dict], root_id: str) -> dict:
    stats = {
        "input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cost": 0,
        "levels": defaultdict(lambda: {"count": 0, "input": 0, "output": 0,
                                        "reasoning": 0, "cache_read": 0, "cost": 0,
                                        "agents": set()}),
    }
    walk(sessions, root_id, 0, stats)
    stats["levels"] = dict(sorted(stats["levels"].items()))
    stats["total"] = (stats["input"] + stats["output"]
                      + stats["cache_read"] + stats["reasoning"])
    return stats


def walk(sessions: dict[str, dict], sid: str, depth: int, stats: dict) -> None:
    s = sessions[sid]
    d = stats["levels"][depth]
    d["count"] += 1
    d["input"] += s["tokens_input"] or 0
    d["output"] += s["tokens_output"] or 0
    d["reasoning"] += s["tokens_reasoning"] or 0
    d["cache_read"] += s["tokens_cache_read"] or 0
    d["cost"] += s["cost"] or 0
    d["agents"].add(s["agent"])
    stats["input"] += s["tokens_input"] or 0
    stats["output"] += s["tokens_output"] or 0
    stats["reasoning"] += s["tokens_reasoning"] or 0
    stats["cache_read"] += s["tokens_cache_read"] or 0
    stats["cost"] += s["cost"] or 0
    for child_id in s["children"]:
        walk(sessions, child_id, depth + 1, stats)


def fmt_k(v: float) -> str:
    return f"{v/1000:.1f}k"


def print_run_detail(run: dict) -> None:
    st = run["stats"]
    root = run["root"]
    print(f"--- Глубина {run['depth']} | агент: {root['agent']} | "
          f"запуск: {ts(root['time_created'])} "
          f"({datetime.fromtimestamp(root['time_created']/1000):%H:%M:%S}) ---")
    print(f"{'Уровень':<10} {'Агенты':<24} {'Сессий':<8} {'Input':<10} {'Output':<9} "
          f"{'CacheRd':<9} {'Reason':<8} {'Итого':<10}")
    print("-" * 100)
    for level, lv in st["levels"].items():
        total = lv["input"] + lv["output"] + lv["cache_read"] + lv["reasoning"]
        agents = ",".join(sorted(lv["agents"]))[:22]
        print(f"{'L'+str(level):<10} {agents:<24} {lv['count']:<8} "
              f"{fmt_k(lv['input']):<10} {fmt_k(lv['output']):<9} "
              f"{fmt_k(lv['cache_read']):<9} {fmt_k(lv['reasoning']):<8} {fmt_k(total):<10}")
    print(f"{'Σ':<10} {'ИТОГО':<24} {'':<8} {fmt_k(st['input']):<10} "
          f"{fmt_k(st['output']):<9} {fmt_k(st['cache_read']):<9} "
          f"{fmt_k(st['reasoning']):<8} {fmt_k(st['total']):<10}")
    print(f"  Стоимость: ${st['cost']:.4f}")
    print()


def print_summary(runs_by_depth: dict[int, list[dict]], all_runs: bool) -> None:
    print("=" * 100)
    print("СВОДКА ПО ВСЕМ ПРОГОНАМ (суммарные токены на глубину)")
    print("=" * 100)
    for depth in sorted(runs_by_depth):
        runs = runs_by_depth[depth]
        totals = [r["stats"]["total"] for r in runs]
        inputs = [r["stats"]["input"] for r in runs]
        outs = [r["stats"]["output"] for r in runs]
        print(f"\nГлубина {depth} — прогонов: {len(runs)}")
        for i, r in enumerate(runs):
            print(f"  run {i+1}: {fmt_k(r['stats']['total']):>8} "
                  f"(input={fmt_k(r['stats']['input'])}, output={fmt_k(r['stats']['output'])}) "
                  f"[{ts(r['root']['time_created'])}]")
        if len(runs) > 1:
            mean_v = statistics.mean(totals)
            stdev_v = statistics.stdev(totals) if len(totals) > 1 else 0.0
            print(f"  среднее:    {fmt_k(mean_v):>8} ± {fmt_k(stdev_v):>7} (σ)")
            print(f"  медиана:    {fmt_k(statistics.median(totals)):>8}")
            print(f"  мин/макс:   {fmt_k(min(totals)):>8} / {fmt_k(max(totals))}")
        else:
            print(f"  (единственный прогон — накоплено {1 - 0} из 3+ для статистики)")

    # Оверхед относительно baseline (среднее по прогонам глубины 0)
    print("\n" + "=" * 100)
    print("ОВЕРХЕД ОТНОСИТЕЛЬНО BASELINE (глубина 0)")
    print("=" * 100)
    base_runs = runs_by_depth.get(0, [])
    if base_runs:
        base_avg = statistics.mean([r["stats"]["total"] for r in base_runs])
        print(f"\nBaseline (глубина 0): среднее {fmt_k(base_avg)} токенов "
              f"(по {len(base_runs)} прогон(ам))")
        print(f"\n{'Глубина':<10} {'Среднее':<12} {'Δ токенов':<12} {'Δ %':<10} "
              f"{'Координация':<12} {'Полезная работа':<15} {'Доля координации':<18}")
        print("-" * 90)
        for depth in sorted(runs_by_depth):
            if depth == 0:
                continue
            runs = runs_by_depth[depth]
            totals = [r["stats"]["total"] for r in runs]
            avg = statistics.mean(totals)
            delta = avg - base_avg
            pct = (delta / base_avg * 100) if base_avg else 0
            # "полезная работа" = листья дерева (последний уровень), "координация" = всё остальное
            coords = []
            leaves = []
            for r in runs:
                st = r["stats"]
                leaf_level = max(st["levels"].keys()) if st["levels"] else 0
                leaf = st["levels"][leaf_level]
                leaf_total = leaf["input"] + leaf["output"] + leaf["cache_read"] + leaf["reasoning"]
                leaves.append(leaf_total)
                coords.append(st["total"] - leaf_total)
            coord_avg = statistics.mean(coords)
            leaf_avg = statistics.mean(leaves)
            coord_share = (coord_avg / avg * 100) if avg else 0
            print(f"{'L'+str(depth):<10} {fmt_k(avg):<12} {fmt_k(delta):<12} "
                  f"{pct:+.1f}%{'':<5} {fmt_k(coord_avg):<12} {fmt_k(leaf_avg):<15} "
                  f"{coord_share:.1f}%")
    else:
        print("База (глубина 0) не найдена. Прогони сначала глубину 0.")


def main():
    ap = argparse.ArgumentParser(description="Валидатор токенов эксперимента с вложенными оркестраторами")
    ap.add_argument("--db", default=DEFAULT_DB, help="путь к opencode.db")
    ap.add_argument("--all", action="store_true", help="показать детали по всем прогонам")
    args = ap.parse_args()

    starts = load_starts()
    if not starts:
        print("Отметки стартов не найдены. Сначала запусти ./nest-exp/run_experiment.sh")
        sys.exit(1)

    sessions = load_sessions(args.db, starts[0])
    if not sessions:
        print("Сессии эксперимента не найдены. Сначала запусти ./nest-exp/run_experiment.sh")
        sys.exit(1)

    trees = build_trees(sessions)
    if not trees:
        print("Корневые сессии эксперимента не найдены. Проверь --title в run_experiment.sh")
        sys.exit(1)

    runs_by_depth: dict[int, list[dict]] = defaultdict(list)
    for t in trees:
        runs_by_depth[t["depth"]].append(t)

    if args.all:
        print("=" * 100)
        print("ДЕТАЛИ ПО ПРОГОНАМ")
        print("=" * 100)
        for depth in sorted(runs_by_depth):
            for run in runs_by_depth[depth]:
                print_run_detail(run)

    print_summary(runs_by_depth, args.all)


if __name__ == "__main__":
    main()
