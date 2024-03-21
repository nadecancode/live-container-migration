import json
import random
import socket
import subprocess
import os.path

import filelock
import ipaddress


def compatible(ip_1, ip_2):
    # Return true if either ip is ipv6, since we don't care
    try:
        if ipaddress.ip_address(ip_1).version == 6 or ipaddress.ip_address(ip_2).version == 6:
            return True
    except:
        return True
    return not ipaddress.ip_network(ip_1, False).overlaps(ipaddress.ip_network(ip_2, False))


def generate_ip():
    # Must be in 10.0.0.0/8, not be in 10.[478]x Validity checking follows later. Gives two addresses in the same /30, but not at the 0 or 3 spots. Does not include the .0 or .255 address. Uses rejection sampling
    while True:
        b = random.randint(1, 254)
        c = random.randint(1, 254)
        # 62 possibilities
        d = random.randint(1, 63)
        if b // 10 == 4 or b // 10 == 7 or b // 10 == 8:
            continue
        return f"10.{b}.{c}.{d * 4 + 1}/30", f"10.{b}.{c}.{d * 4 + 2}/30"


def get_compatible_ips(list_1, list_2):
    while True:
        ip_1, ip_2 = generate_ip()
        valid = True
        for ip in list_1:
            if not compatible(ip, ip_1) or not compatible(ip, ip_2):
                valid = False

        for ip in list_2:
            if not compatible(ip, ip_1) or not compatible(ip, ip_2):
                valid = False

        if not valid:
            continue

        return ip_1, ip_2


def get_if_name(ip):
    # Given ip, prefix wg0 and then the ip with host masked out, dashes instead of dots
    # Assume only /30s are given
    return "wg-" + ip.split(".")[1] + "-" + ip.split(".")[2] + "-" + str(int(ip.split(".")[3].split("/")[0]) // 4 * 4)


"""
def get_port(ip):
    # Given ip, with host masked out, take 14 bits and convert to int
    # We just hope for no collisions here
    a = int(ip.split(".")[1])
    b = int(ip.split(".")[2])
    c = int(ip.split(".")[3].split("/")[0]) // 4
    res = (a << 12) + (b << 6) + c
    res = res % (2**15)
    return res + (2**14)
    
    """


def get_port():
    # Gets a random port > 16384 from the system and returns it
    port = random.randint(16385, 65535)
    # Check if port is in use
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except Exception:
                port = random.randint(16385, 65535)


def get_ips():
    return subprocess.run("ip -o addr show | awk '{print $4}'", shell=True, text=True, capture_output=True).stdout


def setup_migration_routing(iface, mark, table):
    # Add routing
    subprocess.run(f"ip rule add fwmark {mark} lookup {table}", shell=True)
    subprocess.run(f"ip route add default dev {iface} table {table}", shell=True)
    # Add iptables rules
    # Removing podman interface specificity should allow multi-hop routing
    # Even though incoming packets are marked, they get re-marked so don't fall into the custom routing table
    subprocess.run(
        f"iptables -t mangle -A PREROUTING -m mark --mark {mark + 1} -j MARK --set-mark {mark}",
        shell=True)
    subprocess.run(f"iptables -t mangle -A PREROUTING -i {iface} -j MARK --set-mark {mark + 1}", shell=True)
    subprocess.run(f"iptables -t mangle -A PREROUTING -i {iface} -j CONNMARK --save-mark", shell=True)


def teardown_migration_routing(iface, mark, table):
    # Remove routing
    subprocess.run(f"ip rule del fwmark {mark} lookup {table}", shell=True)
    subprocess.run(f"ip route del default dev {iface} table {table}", shell=True)
    # Remove iptables rules
    subprocess.run(
        f"iptables -t mangle -D PREROUTING -m mark --mark {mark + 1} -j MARK --set-mark {mark}",
        shell=True)
    subprocess.run(f"iptables -t mangle -D PREROUTING -i {iface} -j MARK --set-mark {mark + 1}", shell=True)
    subprocess.run(f"iptables -t mangle -D PREROUTING -i {iface} -j CONNMARK --save-mark", shell=True)


def setup_dnat_rule(ip, port):
    # Add dnat rule
    # Maybe the conntrack fairy will visit in the night and leave a more elegant solution under my pillow
    # UPDATE: the conntrack fairy did, this function should be mostly unused now
    subprocess.run(f"iptables -t nat -A PREROUTING -p tcp --dport {port} -j DNAT --to-destination {ip}", shell=True)
    subprocess.run(f"iptables -t nat -A PREROUTING -p udp --dport {port} -j DNAT --to-destination {ip}", shell=True)


def teardown_dnat_rule(ip, port):
    # Remove dnat rule
    subprocess.run(f"iptables -t nat -D PREROUTING -p tcp --dport {port} -j DNAT --to-destination {ip}", shell=True)
    subprocess.run(f"iptables -t nat -D PREROUTING -p udp --dport {port} -j DNAT --to-destination {ip}", shell=True)


def tc_add_qdisc(ifname):
    subprocess.run(f"tc qdisc add dev {ifname} root", shell=True)


def tc_add_latency(ifname, latency):
    subprocess.run(f"tc qdisc add dev {ifname} root netem delay {latency}ms", shell=True)
    pass


def tc_del_latency(ifname):
    subprocess.run(f"tc qdisc change dev {ifname} root netem delay 0ms", shell=True)


def tc_del_qdisc(ifname):
    subprocess.run(f"tc qdisc del dev {ifname} root", shell=True)


def dump_conntrack_entries(container_ip, port):
    output = subprocess.run(f"conntrack -L -p tcp -g {container_ip} --dport {port} -o save", shell=True, text=True,
                            capture_output=True).stdout
    # Split by newline and trim both ends
    entries = []
    for entry in output.split("\n"):
        entry = entry.strip()
        if len(entry) > 0:
            entries.append(entry)

    output = subprocess.run(f"conntrack -L -p udp -g {container_ip} --dport {port} -o save", shell=True, text=True,
                                capture_output=True).stdout
    # Split by newline and trim both ends
    for entry in output.split("\n"):
        entry = entry.strip()
        if len(entry) > 0:
            entries.append(entry)

    output = subprocess.run(f"conntrack -L -p udp -g {container_ip} --dport {port}", shell=True, text=True,
                            capture_output=True).stdout
    unparsed = []
    for entry in output.split("\n"):
        entry = entry.strip()
        if len(entry) > 0:
            unparsed.append(entry)

    output = subprocess.run(f"conntrack -L -p tcp -g {container_ip} --dport {port}", shell=True, text=True,
                            capture_output=True).stdout
    for entry in output.split("\n"):
        entry = entry.strip()
        if len(entry) > 0:
            unparsed.append(entry)

    # Unparsed format: ipv4     2 udp      17 21 src=34.218.249.146 dst=10.25.167.86 sport=44544 dport=5201 src=10.88.0.12 dst=34.218.249.146 sport=5201 dport=44544 [ASSURED] mark=2 use=1
    # We want to find matching entries using protocol, src, dst, sport, and dport, then add the mark to the entry

    real_entries = []
    for entry in unparsed:
        entry_split = entry.split()
        proto = None
        src_ip = None
        dst_ip = None
        src_port = None
        dst_port = None
        mark = None
        for i in range(0, len(entry_split)):
            if entry_split[i] == "udp" or entry_split[i] == "tcp":
                proto = entry_split[i]
                continue
            val = entry_split[i].split("=")
            if len(val) == 0:
                continue
            if val[0] == "src" and src_ip is None:
                src_ip = val[1]
            if val[0] == "dst" and dst_ip is None:
                dst_ip = val[1]
            if val[0] == "sport" and src_port is None:
                src_port = val[1]
            if val[0] == "dport" and dst_port is None:
                dst_port = val[1]
            if val[0] == "mark" and mark is None:
                mark = val[1]
        for parsed_entry in entries:
            parsed_entry_split = parsed_entry.split()
            for i in range(0, len(parsed_entry_split) - 1):
                if parsed_entry_split[i] == "-s":
                    source_ip = parsed_entry_split[i + 1]
                if parsed_entry_split[i] == "--dport":
                    dest_port = parsed_entry_split[i + 1]
                if parsed_entry_split[i] == "--sport":
                    source_port = parsed_entry_split[i + 1]
                if parsed_entry_split[i] == "-d":
                    dest_ip = parsed_entry_split[i + 1]
                if parsed_entry_split[i] == "-p":
                    protocol = parsed_entry_split[i + 1]
            try:
                if source_ip == src_ip and dest_ip == dst_ip and source_port == src_port and dest_port == dst_port and protocol == proto:
                    parsed_entry += " --mark " + mark
                    real_entries.append(parsed_entry)
                    break
            except:
                print("Parse failure")
        else:
            print("No matching entry found")
    print(real_entries)

    return real_entries


# Example of pre entry: -A -t 431996 -u SEEN_REPLY,ASSURED -s 71.34.64.4 -d 172.31.26.253 -g 10.88.0.18 -q 71.34.64.4 -p tcp --sport 47202 --dport 8080 --reply-port-src 80 --reply-port-dst 47202 --state ESTABLISHED
# Example of post entry: -A -t 431962 -u SEEN_REPLY,ASSURED -s 71.34.64.4 -d 172.31.26.253 -g 10.140.67.214 -q 71.34.64.4 -p tcp --sport 47202 --dport 8080 --reply-port-src 8080 --reply-port-dst 47202 --state ESTABLISHED
def rewrite_source_conntrack_entries(entries, container_ip, wg_ip, old_port, new_port):
    wg_ip = wg_ip.split("/")[0]
    for entry in entries:
        # First, delete old entry by splicing out time and using -D instead of -A
        entry_parsed = entry.split(" ")
        del_entry = "-D " + " ".join(entry_parsed[3:])
        # Then, add new entry by changing time and using -A

        valid = True

        for i in range(3, len(entry_parsed), 2):
            if entry_parsed[i] == "-g":
                if entry_parsed[i + 1] != container_ip:
                    valid = False
                entry_parsed[i + 1] = wg_ip
            if entry_parsed[i] == "--reply-port-src":
                if entry_parsed[i + 1] != old_port:
                    valid = False
                entry_parsed[i + 1] = new_port

        if not valid:
            continue

        # brittle parsing code; that is fine for now

        add_entry = "-A " + " ".join(entry_parsed[3:]) + " -t " + entry_parsed[2]

        subprocess.run(f"conntrack {del_entry}", shell=True)
        subprocess.run(f"conntrack {add_entry}", shell=True)

        pass


# Example of dest entry -A -t 431929 -u SEEN_REPLY,ASSURED -s 71.34.64.4 -d 10.140.67.214 -g 10.88.0.18 -q 71.34.64.4 -p tcp --sport 47202 --dport 8080 --reply-port-src 80 --reply-port-dst 47202 --state ESTABLISHED
# Takes the list of entries dumped by above function, but passed over the wire; rewrite only -d entry
def add_dest_conntrack_entries(entries, wg_ip, mark):
    wg_ip = wg_ip.split("/")[0]
    for entry in entries:
        entry_parsed = entry.split(" ")
        for i in range(3, len(entry_parsed), 2):
            if entry_parsed[i] == "-d":
                entry_parsed[i + 1] = wg_ip

        add_entry = "-A " + " ".join(entry_parsed[3:]) + " -t " + entry_parsed[2] + " --mark " + str(mark)

        subprocess.run(f"conntrack {add_entry}", shell=True)


def setup_filter_rule(container_ip):
    # Have to filter otherwise packets could arrive from container between old connection getting removed and new
    # connection being placed. We do this as late as possible to minimize network downtime
    subprocess.run(f"iptables -t filter -I FORWARD -p tcp -s {container_ip} -j DROP", shell=True)
    subprocess.run(f"iptables -t filter -I FORWARD -p udp -s {container_ip} -j DROP", shell=True)


def teardown_filter_rule(container_ip):
    subprocess.run(f"iptables -t filter -D FORWARD -p tcp -s {container_ip} -j DROP", shell=True)
    subprocess.run(f"iptables -t filter -D FORWARD -p udp -s {container_ip} -j DROP", shell=True)


def conntrack_flush():
    subprocess.run("conntrack -F", shell=True)


# Use /tmp so all wg related config is ephemeral on restart
TUNNEL_LOCK_FILE_NAME = "/tmp/tunnels.json.lock"
TUNNEL_FILE_NAME = "/tmp/tunnels.json"
PRIVKEY_NAME = "/tmp/tun.key"
PUBKEY_NAME = "/tmp/tun.pub"
PODMAN_IFACE = "podman0"

lock = filelock.FileLock(TUNNEL_LOCK_FILE_NAME)


def setup_wg_interface(ip_self, ip_peer, peer_real_ip):
    if not is_wg_setup():
        setup_wg()

    if_name = get_if_name(ip_self)

    subprocess.run(f"ip link add {if_name} type wireguard", shell=True)
    subprocess.run(f"ip addr add {ip_self} dev {if_name}", shell=True)

    # Get port for wg, setup listening, and return it
    port = get_port()
    subprocess.run(f"wg set {if_name} private-key {PRIVKEY_NAME} listen-port {port}", shell=True)

    return port


def teardown_wg_interface(if_name):
    # Don't need to delete peers or anything complicated
    subprocess.run(f"ip link del {if_name}", shell=True)


def setup_wg_peer(if_name, ip_peer, peer_pubkey, port):
    if not is_wg_setup():
        setup_wg()

    subprocess.run(f"wg set {if_name} peer {peer_pubkey} endpoint {ip_peer}:{port} allowed-ips 0.0.0.0/0",
                   shell=True)


def activate_wg(if_name):
    subprocess.run(f"ip link set {if_name} up", shell=True)


def get_pubkey():
    with open(PUBKEY_NAME, "r") as f:
        return f.read().strip()


def is_wg_setup():
    # Check if all files exist
    return os.path.exists(TUNNEL_FILE_NAME) and os.path.exists(PRIVKEY_NAME) and os.path.exists(PUBKEY_NAME)


TUN_IF_KEY = "if_name"
TUN_PEER_KEY = "peer_ip"
TUN_THIS_KEY = "this_ip"
TUN_MARK_KEY = "mark"
TUN_TABLE_KEY = "table"
TUN_COMPLETE_KEY = "complete"
TUN_MIGRATION_ROUTING_KEY = "migration_routing"


# Assumed to be called only after restarts (/tmp cleared)
# Please make sure this is actually the case as otherwise iptables rules will break
def setup_wg():
    with lock:
        # setup tunnel file
        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump({"mark": 1, "table": 1031}, f)

    # generate keypair
    subprocess.run("wg genkey > " + PRIVKEY_NAME, shell=True)
    subprocess.run("wg pubkey < " + PRIVKEY_NAME + " > " + PUBKEY_NAME, shell=True)

    # Setup conmark save rule; this is once PER HOST
    # Have to remove podman interface specificity for multihop so it goes through the custom routing table
    subprocess.run(f"iptables -t mangle -A PREROUTING -j CONNMARK --restore-mark", shell=True)

# json handling could be better, unfortunately not atomic and I don't want to deal with locks
# the goal is for this to be good enough at concurrent access even though we won't use it that way in demos or irl
def get_tunnel(dest):
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            return tun[dest]


def add_tunnel(dest, if_name, peer_ip, this_ip):
    with lock:
        mark = increment_and_get_mark()
        table = increment_and_get_table()
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            tun[dest] = {TUN_IF_KEY: if_name, TUN_PEER_KEY: peer_ip, TUN_THIS_KEY: this_ip, TUN_MARK_KEY: mark,
                         TUN_TABLE_KEY: table, TUN_COMPLETE_KEY: False, TUN_MIGRATION_ROUTING_KEY: False}
        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump(tun, f)


def set_tunnel_complete(dest):
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            tun[dest][TUN_COMPLETE_KEY] = True
        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump(tun, f)


def set_tunnel_migration_routing(dest):
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            tun[dest][TUN_MIGRATION_ROUTING_KEY] = True
        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump(tun, f)


def increment_and_get_mark():
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            mark = tun["mark"]
            tun["mark"] += 2
            # TODO: theres an upper bound for these values
        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump(tun, f)
        return mark


def increment_and_get_table():
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            table = tun["table"]
            tun["table"] += 1
            # TODO: theres an upper bound for these values
        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump(tun, f)
        return table


def check_tunnel(dest):
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            return dest in tun


def delete_tunnel(dest):
    with lock:
        with open(TUNNEL_FILE_NAME, "r") as f:
            tun = json.load(f)
            tun.pop(dest)

        with open(TUNNEL_FILE_NAME, "w") as f:
            json.dump(tun, f)
