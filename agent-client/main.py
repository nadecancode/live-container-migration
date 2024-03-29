import argparse
import json
import os
import subprocess
from pathlib import Path

from client import CommunicationClient
from podman import PodmanClient
from state import AgentState, AgentStatus
import sys
from bullet import Bullet, SlidePrompt, Input, Numbers
from exporter import ContainerExporter
from time import perf_counter

import os
import sys
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from common import net

uri = "unix:///run/podman/podman.sock"
client = PodmanClient(base_url=uri)

agent_state = AgentState()

running_containers = client.containers.list(
    filters={
        "status": "running"
    }
)

if len(running_containers) == 0:
    print("No running containers detected in Podman. Try booting up a container first!")
    sys.exit(-1)

cli = SlidePrompt([
    Input("Destination Host: "),
    Numbers("Destination Port: ", type=int),
    Bullet(
        prompt="\nChoose a running container to migrate: ",
        choices=list(
            map(lambda container: container.id, running_containers)
        ),
        indent=0,
        align=5,
        margin=2,
        shift=0,
        bullet="",
        pad_right=5
    )
])

parser = argparse.ArgumentParser()
parser.add_argument("--use-cli-args", action="store_true")
parser.add_argument("--host", type=str, default=None)
parser.add_argument("--port", type=int, default=None)
parser.add_argument("--container_num", type=int, default=None)

args = parser.parse_args()

if not args.use_cli_args:
    result = cli.launch()

    responses = [res[1] for res in result]

    host, port, container_id = responses
else:
    host = args.host
    port = args.port
    container_id = running_containers[args.container_num].id

print(f"Establishing a session with the destination agent at {host}:{port}")
comm_client = CommunicationClient(host, port)

global_start = perf_counter()

start = perf_counter()

if not comm_client.start(container_id):
    print("Failed to establish a connection with the destination agent. Try again later.")
    sys.exit(-1)

agent_state.status = AgentStatus.CONNECTED

stop = perf_counter()

print(f"Connected to the destination agent. Took {stop - start}s")

print("Setting up wireguard tunnel")
start = perf_counter()

# Play ip pingpong
my_ip = comm_client.pingpong_ip()
if my_ip == "":
    print("Failed to get our IP as it appears to the other host. Try again later.")
    sys.exit(-1)

# Wireguard algorithn:
# Check if wireguard state is setup on this node. If not, set it up.
# If it is, check if this connection is fully initialized. Verify that is also the case on the peer, and move on
# Otherwise, if this or peer is partially initialized, kill both
# Now, initialize wireguard
if not net.is_wg_setup():
    net.setup_wg()

tun = None

# wg ips in cidr, host ids not
if net.check_tunnel(host):
    tun = net.get_tunnel(host)

    if not tun[net.TUN_COMPLETE_KEY]:
        # Partially setup; teardown on our end
        net.delete_tunnel(host)
        net.teardown_wg_interface(tun[net.TUN_IF_KEY])
        net.teardown_migration_routing(tun[net.TUN_IF_KEY], tun[net.TUN_MARK_KEY], tun[net.TUN_TABLE_KEY])

        tun = None
    else:
        # Fully setup; verify on their end
        if not comm_client.verify_wg():
            # Partially setup; teardown on our end
            net.delete_tunnel(host)
            net.teardown_wg_interface(tun[net.TUN_IF_KEY])
            # We don't know if migration routing is setup or not, so we teardown it anyway
            net.teardown_migration_routing(tun[net.TUN_IF_KEY], tun[net.TUN_MARK_KEY], tun[net.TUN_TABLE_KEY])

            tun = None
        else:
            # Fully setup; still setup migration routing since we don't know if it's setup on their end
            comm_client.activate_migration_routing()

            # get peer ip
            ip_peer = tun[net.TUN_PEER_KEY]

if tun is None:
    # Teardown on their end
    comm_client.teardown_wg()
    # Now, do full setup
    # First, ip negotiation
    other_ips = comm_client.get_ip_data()
    if len(other_ips) == 0:
        print("Failed to get IP data from the peer. Try again later.")
        sys.exit(-1)
    this_ip = net.get_ips().split()
    ip_self, ip_peer = net.get_compatible_ips(this_ip, other_ips)
    # Do setup locally + get port and pubkey from peer
    # inverted args since we are setting up the peer
    wg_data = comm_client.wg_setup_initial(ip_self, ip_peer)

    if len(wg_data) == 0:
        print("Failed to setup wireguard (peer initial setup). Try again later.")
        sys.exit(-1)
    peer_pubkey = wg_data["pubkey"]
    peer_port = int(wg_data["port"])
    # Get port and pubkey
    this_wg_port = net.setup_wg_interface(ip_self, ip_peer, host)
    pubkey = net.get_pubkey()
    # Add to tunnel.json
    net.add_tunnel(host, net.get_if_name(ip_self), ip_peer, ip_self)
    # Send port and pubkey to peer
    if not comm_client.wg_setup_peer(this_wg_port, pubkey):
        print("Failed to setup wireguard (peer final setup). Try again later.")
        sys.exit(-1)
    # Using port and pubkey from peer, setup interfaces
    net.setup_wg_peer(net.get_if_name(ip_self), host, peer_pubkey, peer_port)
    # Activate interface
    net.activate_wg(net.get_if_name(ip_peer))
    net.set_tunnel_complete(host)
    # Activate peer and migration routing
    if not comm_client.activate_wg() or not comm_client.activate_migration_routing():
        print("Failed to setup wireguard (migration routing/activation). Try again later.")
        sys.exit(-1)

# Get container info
out = subprocess.run(f"podman inspect {container_id} -f json", shell=True, capture_output=True).stdout.decode("utf-8")

container_info = json.loads(out)

if len(out) == 0:
    print("Failed to get container info. Try again later.")
    sys.exit(-1)

container_info = container_info[0]

ports = container_info["NetworkSettings"]["Ports"]
ip = container_info["NetworkSettings"]["IPAddress"]

stop = perf_counter()

print(f"Wireguard tunnel setup. Took {stop - start}s")

print(f"Migrating container {container_id} - Dumping a pre-checkpoint")

start = perf_counter()

agent_state.status = AgentStatus.DUMPING_CHECKPOINT

# we delete and recreate the folder on every run. Race condition w/ multiple clients; TODO: don't do that
subprocess.run(f"rm -rf /tmp/exports", shell=True)
subprocess.run(f"mkdir /tmp/exports", shell=True)

exporter = ContainerExporter(
    client,
    container_id,
    Path("/tmp") / "exports"
)

precheckpoint_path = exporter.precheckpoint()

print("Now transferring pre-checkpoint file...")

if not comm_client.upload(precheckpoint_path, pre=True):
    print("Failed to upload pre-checkpoint to destination server. Try again later.")

    os.remove(precheckpoint_path)
    sys.exit(-1)

agent_state.status = AgentStatus.TRANSPORTING_LEFT_OVER

stop = perf_counter()

print(f"Transferred pre-checkpoint file. Took {stop - start}s")

start = perf_counter()

# net.conntrack_flush() # TODO: get better rules and make this unnecessary
# would make the dnat unnecessary as well, which is nice

# net.tc_add_qdisc(net.get_if_name(peer_ip)) # redundant
net.tc_add_latency(net.get_if_name(ip_peer), 60 * 1000)  # if migration takes >1m we have a problem

# Have to filter packets, otherwise things break
net.setup_filter_rule(ip)

global_entries = []

for internal_port, port_entry in ports.items():
    internal_port = internal_port.split("/")[0]
    for host_port in port_entry:
        entries = net.dump_conntrack_entries(ip, host_port["HostPort"])
        global_entries.extend(entries)
        net.rewrite_source_conntrack_entries(entries, ip, ip_peer, internal_port, host_port["HostPort"])
        # Optional: this allows new connections to be made to the old host, but needs to be cleaned up
        # net.setup_dnat_rule(ip_peer.split("/")[0], int(host_port["HostPort"]))  # uncidr

def net_cleanup(dnat=True):
    net.tc_del_latency(net.get_if_name(ip_peer))
    net.tc_del_qdisc(net.get_if_name(ip_peer))
    net.teardown_filter_rule(ip)
    if dnat:
        for entry in ports.values():
            for host_entry in entry:
                # net.teardown_dnat_rule(ip_peer.split("/")[0], int(host_entry["HostPort"]))  # uncidr
                pass


checkpoint_path = exporter.checkpoint()


stop = perf_counter()

print(f"Generated a checkpoint at path {checkpoint_path.absolute()}. Took {stop - start}s")

print("Transporting checkpoint to the destination agent")

start = perf_counter()

agent_state.status = AgentStatus.TRANSPORTING_INITIAL_CHECKPOINT

if not comm_client.upload(checkpoint_path):
    print("Failed to upload checkpoint to destination server. Try again later.")
    net_cleanup()

    os.remove(checkpoint_path)
    sys.exit(-1)

stop = perf_counter()

print(f"Transferred checkpoint file. Took {stop - start}s")

start = perf_counter()

agent_state.status = AgentStatus.RESTORING_CHECKPOINT

if not comm_client.restore(ip_peer, global_entries):
    print("Failed to restore checkpoint in destination server. Try again later.")
    net_cleanup()

    os.remove(checkpoint_path)
    sys.exit(-1)

net.tc_del_latency(net.get_if_name(ip_peer))

stop = perf_counter()

print(f"Restored container with ID {container_id} at {host}:{port}. Took {stop - start}s")

print("Wrapping up the session with destination node")

agent_state.status = AgentStatus.COMPLETED
comm_client.complete()

print("Destroying the container on this node")
client.containers.remove(container_id, force=True)

net_cleanup(dnat=False)

global_stop = perf_counter()

print(f"Migration Completed. Took ~{global_stop - global_start}s overall.")
