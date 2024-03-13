from pathlib import Path
from podman import PodmanClient
from util import call_podman

class ContainerExporter:
    def __init__(self, client: PodmanClient, container_id: str, destination: Path):
        self.client = client
        self.container_id = container_id
        self.destination = destination

        if not self.client.containers.exists(
            self.container_id
        ):
            raise Exception(f"Container {container_id} does not exist")

    def checkpoint(self):
        response = call_podman(
            f"/v4.9.0/libpod/containers/{self.container_id}/checkpoint?export=true&leaveRunning=true&tcpEstablished=true&keep=true&withPrevious=true",
            method="POST"
        ) # ????? post required but you supply option with query parameter

        path = self.destination / f"checkpoint-{self.container_id}.tar.gz"

        with open(path, "wb") as file:
            file.write(response.content)

        return path

    def precheckpoint(self):
        response = call_podman(
            f"/v4.9.0/libpod/containers/{self.container_id}/checkpoint?export=true&preCheckpoint=true",
            method="POST"
        )  # ????? post required but you supply option with query parameter

        path = self.destination / f"pre-checkpoint-{self.container_id}.tar.gz"

        with open(path, "wb") as file:
            file.write(response.content)

        return path

