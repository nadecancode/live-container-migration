import json
from pathlib import Path

from util.podman import call_podman

from migrator.exporter import ContainerExporter
from communication import server

from podman import PodmanClient

uri = "unix:///run/podman/podman.sock"
client = PodmanClient(base_url=uri)

socket_server = server.SocketServer("0.0.0.0", 50051)
socket_server.listen()

print(f"Listening on {socket_server.host}:{socket_server.port}")

exporter = ContainerExporter(
    client,
    "e86cd7cf0976ff728663018b7954e167b0d59136334646a2f0e2be70212d1199",
    Path("../") / "container" / "exports"
)

print(exporter.checkpoint())
