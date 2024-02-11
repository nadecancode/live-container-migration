import requests_unixsocket
from urllib.parse import quote

podman_sock_uri = f"http+unix://{quote('/run/podman/podman.sock', safe='')}"

def call_podman(path, **kwargs):
    return requests_unixsocket.request(
        url=f"{podman_sock_uri}{path}",
        **kwargs
    )