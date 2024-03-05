import errno
import logging
import os
import re
import subprocess

from util import call_podman

from flask import Flask, request, jsonify
from state import AgentState, AgentStatus, AgentPeer
import threading

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ["tar.gz"]

def silentremove(filename):
    try:
        os.remove(filename)
    except OSError as e: # this would be "except OSError, e:" before Python 2.6
        if e.errno != errno.ENOENT: # errno.ENOENT = no such file or directory
            raise # re-raise exception if a different error occurred

class CommunicationServer:
    def __init__(self, host, port, state: AgentState):
        self.host = host
        self.port = port
        self.state = state

        self.app = Flask(__name__)
        log = logging.getLogger('werkzeug')
        log.disabled = True

        self.checkpoint_path = "/home/cse291/checkpoint.tar.gz"

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

            return jsonify({
                    "message": "Agent connected"
                })

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

        @self.app.route("/restore", methods=["POST"])
        def restore_checkpoint():
            result = subprocess.run(f"podman container restore --tcp-established -i {self.checkpoint_path} --log-level=debug", shell=True, capture_output=True, text=True)

            print(result)
            return result


        @self.app.route("/complete", methods=["POST"])
        def complete_migration():
            if not (state.status == AgentStatus.COMPLETED):
                return jsonify({
                    "error": "Agent has not completed the process yet, cannot mark as complete from our end."
                })

            state.status = AgentStatus.IDLE
            state.peer = None
            state.pin = None
            state.container_id = None

            return jsonify({
                "message": "OK."
            })

    def start(self):
        self.thread = threading.Thread(target=self.app.run, kwargs={'host': self.host, 'port': self.port})
        self.thread.start()

        print(f"Running communication server at {self.host}:{self.port}")
