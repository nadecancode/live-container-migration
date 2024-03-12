import os
from pathlib import Path

from client import CommunicationClient
from podman import PodmanClient
from state import AgentState, AgentStatus
import sys
from bullet import Bullet, SlidePrompt, Input, Numbers
from exporter import ContainerExporter
from time import perf_counter

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
])

result = cli.launch()

responses = [res[1] for res in result]

host, port, container_id = responses

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

print(f"Migrating container {container_id} - Dumping a checkpoint")

start = perf_counter()

agent_state.status = AgentStatus.DUMPING_CHECKPOINT

exporter = ContainerExporter(
    client,
    container_id,
    Path("../") / "container" / "exports"
)

checkpoint_path = exporter.checkpoint()

stop = perf_counter()

print(f"Generated a checkpoint at path {checkpoint_path.absolute()}. Took {stop - start}s")

print("Transporting checkpoint to the destination agent")

start = perf_counter()

agent_state.status = AgentStatus.TRANSPORTING_INITIAL_CHECKPOINT

if not comm_client.upload(checkpoint_path):
    print("Failed to upload checkpoint to destination server. Try again later.")

    os.remove(checkpoint_path)
    sys.exit(-1)

stop = perf_counter()

print(f"Transferred checkpoint file. Took {stop - start}s")

print("Now transferring pre-checkpoint file...")

start = perf_counter()

agent_state.status = AgentStatus.TRANSPORTING_LEFT_OVER

precheckpoint_path = exporter.precheckpoint()
if not comm_client.upload(precheckpoint_path, pre=True):
    print("Failed to upload pre-checkpoint to destination server. Try again later.")

    os.remove(precheckpoint_path)
    sys.exit(-1)

stop = perf_counter()

print(f"Transferred pre-checkpoint file. Took {stop - start}s")

start = perf_counter()

agent_state.status = AgentStatus.RESTORING_CHECKPOINT

if not comm_client.restore():
    print("Failed to restore checkpoint in destination server. Try again later.")

    os.remove(checkpoint_path)
    sys.exit(-1)

stop = perf_counter()

print(f"Restored container with ID {container_id} at {host}:{port}. Took {stop - start}s")

print("Wrapping up the session with destination node")

agent_state.status = AgentStatus.COMPLETED
comm_client.complete()

print("Destroying the container on this node")
client.containers.remove(container_id, force=True)

global_stop = perf_counter()

print(f"Migration Completed. Took ~{global_stop - global_start}s overall.")
