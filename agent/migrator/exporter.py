from pathlib import Path
from podman import PodmanClient
from util.podman import call_podman

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
            f"/v4.9.0/libpod/containers/{self.container_id}/checkpoint",
            method="POST",
            json={
                "export": True,
                "keep": True,
                "leaveRunning": True,
                "printStats": True,
                "tcpEstablished": True
            }
        )

        path = self.destination / f"checkpoint-{self.container_id}.tar.gz"

        with open(path, "wb") as file:
            file.write(response.content)

        print(response.headers)
        return path