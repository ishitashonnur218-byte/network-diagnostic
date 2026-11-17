#!/usr/bin/env python3
"""UDP echo server used by the network diagnostic client."""

import argparse
import socket


def main():
    parser = argparse.ArgumentParser(description="UDP echo server for network diagnostics.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5005)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind((args.host, args.port))
        print(f"UDP echo server listening on {args.host}:{args.port}", flush=True)
        while True:
            data, client_addr = server.recvfrom(65535)
            server.sendto(data, client_addr)


if __name__ == "__main__":
    main()
