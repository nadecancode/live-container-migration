import json
from pathlib import Path

# from grpc import agent_pb2_grpc, agent_pb2

from bullet import Bullet
from migrator.exporter import ContainerExporter
from communication.transporter import CheckpointTransporter

from communication import server
from communication import client

from podman import PodmanClient

uri = "unix:///run/podman/podman.sock"
client = PodmanClient(base_url=uri)

socket_server = server.SocketServer("0.0.0.0", 50051)
# socket_server = socket_server.construct()

current_container_id = None # TODO - Save a currently migrating session here

running_containers = client.containers.list(
    filters={
        "status": "running"
    }
)

print(f"Listening on {socket_server.host}:{socket_server.port}")

cli = Bullet(
    prompt = "\nChoose a running container to migrate: ",
    choices=list(
        map(lambda container: container.id, running_containers)
    ),
    indent = 0,
    align = 5,
    margin = 2,
    shift = 0,
    bullet = "",
    pad_right = 5
)

container_id = cli.launch()

print(f"Migrating container {container_id} - Exporting")

exporter = ContainerExporter(
    client,
    container_id,
    Path("../") / "container" / "exports"
)

checkpoint_path = exporter.checkpoint()

print(f"Generated a checkpoint at path {checkpoint_path.absolute()}")
key_path = Path(".") / ".." / "credential" / "dest_key"

transporter = CheckpointTransporter(
    checkpoint_path,
    "/home/cse291/checkpoint.tar.gz",
    key_path,
    "18.237.90.46"
)

print(f"Transporting the checkpoint to destination")
transporter.transport()

print("Done")