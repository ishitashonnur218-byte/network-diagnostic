import networkx as nx

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    DEAD_DISPATCHER,
    set_ev_cls
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import packet, ethernet, arp, ipv4
from os_ken.topology import event
from os_ken.topology.api import get_switch

import path_analysis

LEARNED_COOKIE = 0x1   # tags learned flows so they can be flushed


class LearningSwitch(app_manager.OSKenApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(LearningSwitch, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        # (dpid_a, port_a, dpid_b, port_b) with dpid_a < dpid_b
        self.links = set()
        self.failed_links = set()
        self.tree_links = set()
        self.blocked_ports = {}
        # mac -> {"name": str, "dpid": int, "port": int}
        self.hosts = {}

    # ------------------------------------------------------------------
    # Switch connection handling
    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.datapaths[datapath.id] = datapath

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER
            )
        ]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPStateChange, [DEAD_DISPATCHER])
    def state_change_handler(self, ev):
        if ev.datapath and ev.datapath.id in self.datapaths:
            del self.datapaths[ev.datapath.id]

    def add_flow(self, datapath, priority, match, actions,
                 idle_timeout=0, cookie=0):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS, actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            cookie=cookie,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout
        )
        datapath.send_msg(mod)

    def flush_learned_flows(self):
        """Delete only learned flows (keeps the table-miss entry)."""
        for dp in self.datapaths.values():
            ofproto = dp.ofproto
            parser = dp.ofproto_parser
            mod = parser.OFPFlowMod(
                datapath=dp,
                table_id=ofproto.OFPTT_ALL,
                command=ofproto.OFPFC_DELETE,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY,
                cookie=LEARNED_COOKIE,
                cookie_mask=0xffffffffffffffff,
                match=parser.OFPMatch()
            )
            dp.send_msg(mod)

    # ------------------------------------------------------------------
    # Loop prevention: spanning tree from discovered links
    # ------------------------------------------------------------------
    def update_spanning_tree(self):
        ordered = sorted(self.links)

        G = nx.Graph()
        for a, _, b, _ in ordered:
            G.add_edge(a, b)

        tree = nx.Graph()
        tree.add_nodes_from(G.nodes)
        for a, b in sorted(G.edges):
            tree.add_edge(a, b)
            if not nx.is_forest(tree):
                tree.remove_edge(a, b)

        blocked = {}
        kept = set()
        for link in ordered:
            a, pa, b, pb = link
            if tree.has_edge(a, b) and (a, b) not in {(k[0], k[2]) for k in kept}:
                kept.add(link)
                continue
            blocked.setdefault(a, set()).add(pa)
            blocked.setdefault(b, set()).add(pb)

        self.tree_links = kept
        self.blocked_ports = blocked

        # Learned locations and installed flows may now be wrong
        self.mac_to_port.clear()
        self.flush_learned_flows()

        self.logger.info("Blocked (non-tree) ports: %s", blocked)

    def flood_ports(self, datapath, in_port):
        switches = get_switch(self, datapath.id)
        if not switches:
            return None
        blocked = self.blocked_ports.get(datapath.id, set())
        return [
            p.port_no for p in switches[0].ports
            if p.port_no != in_port and p.port_no not in blocked
        ]

    # ------------------------------------------------------------------
    # Host discovery
    # ------------------------------------------------------------------
    def inter_switch_ports(self, dpid):
        ports = set()
        for a, pa, b, pb in self.links | self.failed_links:
            if a == dpid:
                ports.add(pa)
            if b == dpid:
                ports.add(pb)
        return ports

    def learn_host(self, pkt, eth, dpid, in_port):
        """Record a host if the packet came in on a host-facing port."""
        # Need link discovery to know which ports are inter-switch ports
        link_ports = self.inter_switch_ports(dpid)
        if not link_ports or in_port in link_ports:
            return
        # Ignore broadcast / multicast sources
        if int(eth.src.split(":")[0], 16) & 1:
            return

        ip = None
        a = pkt.get_protocol(arp.arp)
        if a is not None:
            ip = a.src_ip
        else:
            v4 = pkt.get_protocol(ipv4.ipv4)
            if v4 is not None:
                ip = v4.src

        # Only record a host once its IP is known (skips IPv6/probe noise)
        if not ip or ip == "0.0.0.0":
            return

        name = "h" + ip.split(".")[-1]       # 10.0.0.1 -> h1

        old = self.hosts.get(eth.src)
        new = {"name": name, "dpid": dpid, "port": in_port}
        if old == new:
            return

        self.hosts[eth.src] = new
        self.logger.info(
            "Host detected: %s (MAC %s) attached to Switch %s Port %s",
            name, eth.src, dpid, in_port
        )
        self.report_paths()

    # ------------------------------------------------------------------
    # Path reporting
    # ------------------------------------------------------------------
    def report_paths(self):
        hosts = {h["name"]: (h["dpid"], h["port"])
                 for h in self.hosts.values()}
        if len(hosts) < 2:
            self.logger.info("Path report: waiting for at least 2 hosts")
            return
        text = path_analysis.report_all_pairs(
            self.links, self.failed_links, self.tree_links, hosts
        )
        self.logger.info("\n%s", text)

    # ------------------------------------------------------------------
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None or eth.ethertype == 0x88cc:
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})

        src = eth.src
        dst = eth.dst

        # Never learn from a port that is blocked by the spanning tree
        if in_port in self.blocked_ports.get(dpid, set()):
            return

        self.learn_host(pkt, eth, dpid, in_port)

        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_ports = [self.mac_to_port[dpid][dst]]
        else:
            out_ports = self.flood_ports(datapath, in_port)
            if out_ports is None:
                # Topology not known yet: drop rather than risk a storm
                return

        actions = [parser.OFPActionOutput(p) for p in out_ports]

        if len(out_ports) == 1 and dst in self.mac_to_port[dpid]:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_src=src,
                eth_dst=dst
            )
            self.add_flow(datapath, 1, match, actions,
                          idle_timeout=30, cookie=LEARNED_COOKIE)

        data = (
            None if msg.buffer_id != ofproto.OFP_NO_BUFFER
            else msg.data
        )

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    # ------------------------------------------------------------------
    # Topology discovery and failure detection
    # ------------------------------------------------------------------
    @set_ev_cls(event.EventSwitchEnter)
    def switch_enter_handler(self, ev):
        self.logger.info("Switch detected: %s", ev.switch.dp.id)

    @staticmethod
    def normalise(src, dst):
        if src.dpid < dst.dpid:
            return (src.dpid, src.port_no, dst.dpid, dst.port_no)
        return (dst.dpid, dst.port_no, src.dpid, src.port_no)

    @set_ev_cls(event.EventLinkAdd)
    def link_add_handler(self, ev):
        src = ev.link.src
        dst = ev.link.dst

        self.logger.info(
            "Link detected: Switch %s Port %s <-> Switch %s Port %s",
            src.dpid, src.port_no, dst.dpid, dst.port_no
        )

        if src.dpid == dst.dpid:
            return
        link = self.normalise(src, dst)

        if link in self.links:
            return
        self.links.add(link)
        if link in self.failed_links:
            self.logger.info("Link RESTORED: s%s <-> s%s", link[0], link[2])
            self.failed_links.discard(link)

        self.update_spanning_tree()
        self.report_paths()

    @set_ev_cls(event.EventLinkDelete)
    def link_delete_handler(self, ev):
        src = ev.link.src
        dst = ev.link.dst
        link = self.normalise(src, dst)

        if link not in self.links:
            return

        self.logger.warning(
            "LINK FAILURE detected: Switch %s Port %s <-> Switch %s Port %s",
            link[0], link[1], link[2], link[3]
        )
        self.links.discard(link)
        self.failed_links.add(link)

        self.update_spanning_tree()
        self.report_paths()
