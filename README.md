# Network Diagnostic and Path Analysis Tool

A Python-based network diagnostic tool that combines **Software-Defined Networking (SDN), Mininet, UDP socket programming and NetworkX** to monitor network performance and analyse network paths.

## Features
- UDP-based network communication.
- Measurement of RTT, packet loss and goodput.
- Network topology discovery and path analysis.
- Link failure detection using an SDN controller.
- Identification of alternative paths.
- Performance comparison using weighted metrics.

## Technologies Used
- Python
- Mininet
- OS-Ken
- OpenFlow 1.3
- NetworkX
- UDP Sockets

## Network Topology

The project uses a diamond topology with two hosts (h1, h2) and four switches (s1, s2, s3, s4).

Two alternative paths connect the hosts:

- `h1 → s1 → s2 → s4 → h2`
- `h1 → s1 → s3 → s4 → h2`

## Path Analysis

The project uses NetworkX's `all_simple_paths()` to identify possible paths and selects the shortest path based on hop count.

## Future Enhancements
- Dynamic performance-based routing.
- Real-time monitoring dashboard.
- Support for larger network topologies.
- Additional network performance metrics.

## Contributors
Developed as an academic networking project.

## References
- [Mininet](https://mininet.org/)
- [OS-Ken](https://docs.openstack.org/os-ken/)
- [NetworkX](https://networkx.org/documentation/stable/)
- [Python Socket Programming](https://docs.python.org/3/library/socket.html)
