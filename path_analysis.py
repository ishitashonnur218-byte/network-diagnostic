import itertools
import networkx as nx


def build_graph(links, hosts):
    """
    links: iterable of (dpid_a, port_a, dpid_b, port_b)
    hosts: dict {host_name: (dpid, port)}
    """
    G = nx.Graph()
    for a, _, b, _ in links:
        G.add_edge(f"s{a}", f"s{b}")
    for name, (dpid, _port) in hosts.items():
        G.add_edge(name, f"s{dpid}")
    return G


def find_paths(G, source, destination):
    """Return (all simple paths sorted by length, shortest path or None)."""
    if source not in G or destination not in G:
        return [], None
    if not nx.has_path(G, source, destination):
        return [], None
    paths = sorted(
        nx.all_simple_paths(G, source, destination),
        key=lambda p: (len(p), p)
    )
    return paths, paths[0]


def link_name(link):
    a, _, b, _ = link
    return f"s{a}-s{b}"


def report(source, destination, links, failed_links, active_links, hosts):
    """
    links:        links currently up
    failed_links: links that were seen going down
    active_links: links the controller actually forwards over (spanning tree)
    Returns the report as a string.
    """
    G_now = build_graph(links, hosts)
    G_all = build_graph(set(links) | set(failed_links), hosts)
    G_active = build_graph(active_links, hosts)

    available, shortest = find_paths(G_now, source, destination)
    all_paths, _ = find_paths(G_all, source, destination)
    failed = [p for p in all_paths if p not in available]
    active_paths, _ = find_paths(G_active, source, destination)

    lines = []
    lines.append("=" * 60)
    lines.append(f"PATH REPORT: {source} -> {destination}")
    lines.append("=" * 60)

    if failed_links:
        lines.append("Failed links: " +
                     ", ".join(sorted(link_name(l) for l in failed_links)))
    else:
        lines.append("Failed links: none")

    lines.append(f"\nAvailable paths ({len(available)}):")
    for i, p in enumerate(available, 1):
        lines.append(f"  Path {i}: {' -> '.join(p)}")
    if not available:
        lines.append("  NONE - destination unreachable")

    lines.append(f"\nFailed paths ({len(failed)}):")
    for i, p in enumerate(failed, 1):
        lines.append(f"  Path {i}: {' -> '.join(p)}")
    if not failed:
        lines.append("  none")

    if shortest:
        lines.append(f"\nShortest available path: {' -> '.join(shortest)}"
                     f"  ({len(shortest) - 1} links)")
    if active_paths:
        lines.append(f"Path used by traffic (loop-free tree): "
                     f"{' -> '.join(active_paths[0])}"
                     f"  ({len(active_paths[0]) - 1} links)")
    lines.append("=" * 60)
    return "\n".join(lines)


def report_all_pairs(links, failed_links, active_links, hosts):
    out = []
    for src, dst in itertools.combinations(sorted(hosts), 2):
        out.append(report(src, dst, links, failed_links,
                          active_links, hosts))
    return "\n".join(out)


if __name__ == "__main__":
    # Standalone demo with the known diamond topology
    demo_links = [(1, 2, 2, 1), (2, 2, 4, 1), (1, 3, 3, 1), (3, 2, 4, 2)]
    demo_hosts = {"h1": (1, 1), "h2": (4, 3)}
    print(report("h1", "h2", demo_links, [], demo_links[:3], demo_hosts))
