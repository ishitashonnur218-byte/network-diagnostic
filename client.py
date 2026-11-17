#!/usr/bin/env python3
"""UDP network diagnostic client with machine-readable performance metrics."""

import argparse
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Measure UDP echo RTT, loss and goodput.")
    parser.add_argument("--server", default="10.0.0.2", help="UDP echo server IP (default: 10.0.0.2)")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--probes", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--payload-bytes", type=int, default=512)
    parser.add_argument("--path-label", default="unlabelled", help="Label of the path being measured")
    parser.add_argument("--output", default="udp_metrics.json", help="JSON metrics output file")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.probes < 1 or args.timeout <= 0 or args.interval < 0:
        raise SystemExit("probes must be >= 1, timeout > 0 and interval >= 0")
    if args.payload_bytes < 32 or args.payload_bytes > 60000:
        raise SystemExit("payload-bytes must be between 32 and 60000")

    header_size = len(f"NDIAG|{args.probes:08d}|".encode())
    if args.payload_bytes < header_size:
        raise SystemExit(f"payload-bytes must be at least {header_size}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(args.timeout)
    sent = received = 0
    rtts_ms = []
    total_start = time.perf_counter()

    print(f"UDP diagnostic: {args.server}:{args.port}")
    print(f"Path: {args.path_label} | probes: {args.probes} | payload: {args.payload_bytes} bytes")

    try:
        for seq in range(1, args.probes + 1):
            prefix = f"NDIAG|{seq:08d}|".encode()
            payload = prefix + (b"x" * (args.payload_bytes - len(prefix)))
            sent += 1
            probe_start = time.perf_counter()
            try:
                sock.sendto(payload, (args.server, args.port))
                reply, _peer = sock.recvfrom(65535)
                rtt = (time.perf_counter() - probe_start) * 1000.0
                if reply == payload:
                    received += 1
                    rtts_ms.append(rtt)
                    print(f"Probe {seq:02d}: reply, RTT={rtt:.3f} ms")
                else:
                    print(f"Probe {seq:02d}: invalid echo")
            except socket.timeout:
                print(f"Probe {seq:02d}: timeout")
            except OSError as exc:
                print(f"Probe {seq:02d}: socket error: {exc}")
            if args.interval and seq != args.probes:
                time.sleep(args.interval)
    finally:
        sock.close()

    duration = max(time.perf_counter() - total_start, 1e-9)
    lost = sent - received
    loss_pct = (lost / sent) * 100.0
    avg_rtt = (sum(rtts_ms) / len(rtts_ms)) if rtts_ms else None
    min_rtt = min(rtts_ms) if rtts_ms else None
    max_rtt = max(rtts_ms) if rtts_ms else None
    # Application-level echoed payload goodput; this is not raw link capacity.
    goodput_mbps = (received * args.payload_bytes * 8.0) / duration / 1_000_000.0

    result = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "path_label": args.path_label,
        "server_ip": args.server,
        "port": args.port,
        "probes_sent": sent,
        "probes_received": received,
        "probes_lost": lost,
        "packet_loss_percent": round(loss_pct, 4),
        "avg_rtt_ms": round(avg_rtt, 4) if avg_rtt is not None else None,
        "min_rtt_ms": round(min_rtt, 4) if min_rtt is not None else None,
        "max_rtt_ms": round(max_rtt, 4) if max_rtt is not None else None,
        "rtt_samples_ms": [round(v, 4) for v in rtts_ms],
        "payload_bytes": args.payload_bytes,
        "duration_seconds": round(duration, 6),
        "goodput_mbps": round(goodput_mbps, 6),
        "goodput_definition": "echoed application payload bits divided by total measurement duration"
    }

    output = Path(args.output)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("\n--- UDP diagnostic summary ---")
    print(f"Sent/received/lost: {sent}/{received}/{lost}")
    print(f"Packet loss: {loss_pct:.2f}%")
    print(f"Average RTT: {avg_rtt:.3f} ms" if avg_rtt is not None else "Average RTT: N/A")
    print(f"Application goodput: {goodput_mbps:.6f} Mbps")
    print(f"Metrics saved to: {output}")


if __name__ == "__main__":
    main()
