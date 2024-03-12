import errno
import logging
import os
import re
import subprocess

import os
import sys
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from common.net import get_ips
from common import net
from util import call_podman

from flask import Flask, request, jsonify
from state import AgentState, AgentStatus, AgentPeer
import threading


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ["tar.gz"]


def silentremove(filename):
    try:
        os.remove(filename)
    except OSError as e:  # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
            raise  # re-raise exception if a different error occurred


class CommunicationServer:
    def __init__(self, host, port, state: AgentState):
        self.host = host
        self.port = port
        self.state = state

        self.app = Flask(__name__)
        log = logging.getLogger('werkzeug')
        log.disabled = True

        self.checkpoint_path = "/home/cse291/checkpoint.tar.gz"
        self.precheckpoint_path = "/home/cse291/pre-checkpoint.tar.gz"

        @self.app.route("/")
        def index():
            return "Yum Yum"

        @self.app.route("/start", methods=["POST"])
        def start_migration():
            if not (state.status == AgentStatus.IDLE):
                return jsonify({
                    "error": "Agent is not idle"
                })

            state.status = AgentStatus.CONNECTED
            state.peer = AgentPeer(request.remote_addr, -1)

            silentremove(self.checkpoint_path)

            data = request.json
            container_id = data["container_id"]

            state.container_id = container_id

            return "OK"

        @self.app.route("/upload-checkpoint", methods=["POST"])
        def upload_checkpoint():
            state.status = AgentStatus.TRANSPORTING_INITIAL_CHECKPOINT

            range_header = request.headers.get('Range')
            match = re.search('(?P<start>\d+)-(?P<end>\d+)/(?P<total_bytes>\d+)', range_header)
            start = int(match.group('start'))

            with open(self.checkpoint_path, 'rb+' if os.path.exists(self.checkpoint_path) else 'wb+') as f:
                f.seek(start)
                chunk = request.stream.read(1024 * 1024)
                f.write(chunk)

            return "OK"

        @self.app.route("/upload-pre-checkpoint", methods=["POST"])
        def upload_precheckpoint():
            state.status = AgentStatus.TRANSPORTING_LEFT_OVER

            range_header = request.headers.get('Range')
            match = re.search('(?P<start>\d+)-(?P<end>\d+)/(?P<total_bytes>\d+)', range_header)
            start = int(match.group('start'))

            with open(self.precheckpoint_path, 'rb+' if os.path.exists(self.precheckpoint_path) else 'wb+') as f:
                f.seek(start)
                chunk = request.stream.read(1024 * 1024)
                f.write(chunk)

            return "OK"

        @self.app.route("/restore", methods=["POST"])
        def restore_checkpoint():
            try:
                data = request.json
                container_ip = data["container_ip"]
                net.setup_filter_rule(container_ip)
                subprocess.check_call(
                    f"podman container restore --tcp-established -i {self.checkpoint_path} --import-previous={self.precheckpoint_path} --log-level=debug",
                    shell=True, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                net.teardown_filter_rule(container_ip)
            except subprocess.CalledProcessError:
                return "Failed to restore", 502

            state.status = AgentStatus.COMPLETED

            return "OK"

        @self.app.route("/complete", methods=["POST"])
        def complete_migration():
            if not (state.status == AgentStatus.COMPLETED):
                return "Agent has not completed the process yet, cannot mark as complete from our end.", 401

            state.status = AgentStatus.IDLE
            state.peer = None
            state.pin = None
            state.container_id = None

            silentremove(self.checkpoint_path)
            silentremove(self.precheckpoint_path)

            return "OK"

        @self.app.route("/ip_data", methods=["GET"])
        def ip_data():
            return get_ips()

        @self.app.route("/pingpong_ip", methods=["GET"])
        def pingpong_ip():
            return request.remote_addr

        @self.app.route("/teardown_wg", methods=["POST"])
        def teardown_wg():
            dest = request.remote_addr
            # Invariant of the system that wg tunnel.json is setup
            if net.check_tunnel(dest):
                tun = net.get_tunnel(dest)
                net.delete_tunnel(dest)
                net.teardown_wg_interface(tun[net.TUN_IF_KEY])
                net.teardown_migration_routing(tun[net.TUN_IF_KEY], tun[net.TUN_MARK_KEY], tun[net.TUN_TABLE_KEY])

            return "OK"

        @self.app.route("/wg_setup_initial", methods=["POST"])
        def wg_setup_initial():
            # Returns the port to listen and the pubkey, and sets up the tunnel.json
            dest = request.remote_addr

            pubkey = net.get_pubkey()

            data = request.json
            this_ip = data["this_ip"]
            peer_ip = data["peer_ip"]

            port = net.setup_wg_interface(this_ip, peer_ip, dest)
            net.add_tunnel(dest, net.get_if_name(this_ip), peer_ip, this_ip)

            return {"port": port, "pubkey": pubkey}

        @self.app.route("/wg_setup_peer", methods=["POST"])
        def wg_setup_peer():
            # Sets up the peer
            dest = request.remote_addr
            data = request.json
            port = data["peer_port"]
            pubkey = data["peer_pubkey"]

            net.setup_wg_peer(dest, pubkey, port)

            return "OK"

        @self.app.route("/activate_wg", methods=["GET"])
        def activate_wg():
            # Activates the wg interface
            dest = request.remote_addr

            if net.check_tunnel(dest):
                tun = net.get_tunnel(dest)
                net.activate_wg(tun[net.TUN_IF_KEY])
                net.set_tunnel_complete(dest)

            return "OK"

        @self.app.route("/activate_migration_routing", methods=["GET"])
        def activate_migration_routing():
            # Activates the migration routing
            dest = request.remote_addr

            if net.check_tunnel(dest):
                tun = net.get_tunnel(dest)
                if not tun[net.TUN_MIGRATION_ROUTING_KEY]:
                    net.setup_migration_routing(tun[net.TUN_IF_KEY], tun[net.TUN_MARK_KEY], tun[net.TUN_TABLE_KEY])
                    net.set_tunnel_migration_routing(dest)

            return "OK"

        def verify_wg():
            # Verifies the wg interface
            dest = request.remote_addr

            if net.check_tunnel(dest):
                tun = net.get_tunnel(dest)
                return str(int(tun[net.TUN_COMPLETE_KEY]))

            return "0"

    def start(self):
        self.thread = threading.Thread(target=self.app.run, kwargs={'host': self.host, 'port': self.port})
        self.thread.start()

        print(f"Running communication server at {self.host}:{self.port}")
