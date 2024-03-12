from podman import PodmanClient

import os
import sys
import inspect

currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(currentdir)
sys.path.insert(0, parentdir)

from common.net import is_wg_setup, setup_wg
from state import AgentState
import server

uri = "unix:///run/podman/podman.sock"
client = PodmanClient(base_url=uri)

agent_state = AgentState()
comm_server = server.CommunicationServer("0.0.0.0", 50051, agent_state)

if not is_wg_setup():
    setup_wg()

comm_server.start()
