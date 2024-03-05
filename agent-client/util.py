from urllib.parse import quote

import requests_unixsocket

podman_sock_uri = f"http+unix://{quote('/run/podman/podman.sock', safe='')}"

def call_podman(path, **kwargs):
    return requests_unixsocket.request(
        url=f"{podman_sock_uri}{path}",
        **kwargs
    )

