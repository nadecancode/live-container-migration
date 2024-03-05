from podman import PodmanClient
from state import AgentState
import server

uri = "unix:///run/podman/podman.sock"
client = PodmanClient(base_url=uri)

agent_state = AgentState()
comm_server = server.CommunicationServer("0.0.0.0", 50051, agent_state)

comm_server.start()
