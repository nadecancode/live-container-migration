from pathlib import Path
import paramiko
from paramiko import SSHClient
from scp import SCPClient

class CheckpointTransporter:
    def __init__(self, source, destination, private_key, host):
        self.source = source
        self.host = host
        self.destination = destination
        self.private_key = private_key

    def transport(self):
        ssh = SSHClient()

        key = paramiko.Ed25519Key.from_private_key_file(self.private_key)

        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        ssh.connect(self.host, pkey=key)

        scp = SCPClient(ssh.get_transport())

        scp.put(self.source, remote_path=self.destination)
        scp.close()

        return self.destination
