#!/usr/bin/env python3
"""Correlate UDP measurements with the project's diamond SDN paths.

This module deliberately keeps performance analysis separate from the OS-Ken
controller. It consumes the JSON emitted by client.py and uses the same
path_analysis helpers as the existing project.
"""

import argparse
import json
import math
from pathlib import Path

import path_analysis

# Port numbers match the supplied topology.py and observed Mininet `net` output.
DIAMOND_LINKS = {
    (1, 2, 2, 1),  # s1-s2
    (1, 3, 3, 1),  # s1-s3
    (2, 2, 4, 1),  # s2-s4
    (3, 2, 4, 2),  # s3-s4
}
DIAMOND_HOSTS = {"h1": (1, 1), "h2": (4, 3)}


def _edge_name(a, b):
    return tuple(sorted((a, b)))


def diamond_paths(failed_link=None):
    """Return current simple paths for the supplied diamond topology."""
    links = set(DIAMOND_LINKS)
    if failed_link:
        a, b = failed_link
        links = {link for link in links if _edge_name(f"s{link[0]}", f"s{link[2]}") != _edge_name(a, b)}
    graph = path_analysis.build_graph(links, DIAMOND_HOSTS)
    paths, _shortest = path_analysis.find_paths(graph, "h1", "h2")
    return paths


def analyse_failure(failed_link):
    before = diamond_paths()
    after = diamond_paths(failed_link)
    before_set = {tuple(p) for p in before}
    after_set = {tuple(p) for p in after}
    lost = sorted(before_set - after_set)
    return {
        "failed_link": "-".join(failed_link),
        "paths_before": [list(p) for p in before],
        "paths_after": [list(p) for p in after],
        "paths_lost": [list(p) for p in lost],
        "destination_reachable": bool(after),
        "remaining_path_count": len(after),
    }


def load_measurement(filename):
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    required = ("path_label", "packet_loss_percent", "goodput_mbps", "avg_rtt_ms")
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{filename}: missing fields: {', '.join(missing)}")
    return data


def _normalise(values, lower_is_better):
    valid = [v for v in values if v is not None and math.isfinite(float(v))]
    if not valid:
        return [0.0 for _ in values]
    low, high = min(valid), max(valid)
    if math.isclose(low, high):
        return [0.5 if v is not None else 0.0 for v in values]
    scores = []
    for value in values:
        if value is None:
            scores.append(0.0)
        else:
            fraction = (float(value) - low) / (high - low)
            scores.append(1.0 - fraction if lower_is_better else fraction)
    return scores


def compare_measurements(records):
    """Rank measured paths: 40% RTT, 40% loss, 20% application goodput."""
    if len(records) < 2:
        raise ValueError("At least two path measurement JSON files are required")
    rtt = _normalise([r["avg_rtt_ms"] for r in records], True)
    loss = _normalise([r["packet_loss_percent"] for r in records], True)
    goodput = _normalise([r["goodput_mbps"] for r in records], False)
    ranked = []
    for i, record in enumerate(records):
        score = 100.0 * (0.4 * rtt[i] + 0.4 * loss[i] + 0.2 * goodput[i])
        ranked.append({
            "path_label": record["path_label"],
            "avg_rtt_ms": record["avg_rtt_ms"],
            "packet_loss_percent": record["packet_loss_percent"],
            "goodput_mbps": record["goodput_mbps"],
            "score": round(score, 2),
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def print_paths():
    print("Candidate h1-to-h2 paths in the physical diamond topology:")
    for index, path in enumerate(diamond_paths(), 1):
        print(f"  {index}. {' -> '.join(path)}")


def main():
    parser = argparse.ArgumentParser(description="SDN performance integration and path analysis")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("paths", help="list physical candidate paths")
    fail_parser = sub.add_parser("failure", help="analyse the effect of one failed inter-switch link")
    fail_parser.add_argument("--link", required=True, choices=("s1-s2", "s1-s3", "s2-s4", "s3-s4"))
    compare_parser = sub.add_parser("compare", help="compare two or more client metrics JSON files")
    compare_parser.add_argument("files", nargs="+", help="JSON files written by client.py")
    args = parser.parse_args()

    if args.command == "paths":
        print_paths()
    elif args.command == "failure":
        result = analyse_failure(tuple(args.link.split("-")))
        print(json.dumps(result, indent=2))
    elif args.command == "compare":
        records = [load_measurement(name) for name in args.files]
        ranked = compare_measurements(records)
        print("Path performance ranking (score: 40% RTT, 40% packet loss, 20% application goodput):")
        for position, item in enumerate(ranked, 1):
            print(f"{position}. {item['path_label']} | score={item['score']:.2f} | "
                  f"RTT={item['avg_rtt_ms']} ms | loss={item['packet_loss_percent']}% | "
                  f"goodput={item['goodput_mbps']} Mbps")
        print(f"\nBest measured path: {ranked[0]['path_label']}")


if __name__ == "__main__":
    main()
