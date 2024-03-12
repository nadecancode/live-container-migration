import json
import math
import os
import time

import requests


class CommunicationClient:
    def __init__(self, host, port):
        self.base_url = f"http://{host}:{port}"
        self.chunk_size = 1024 * 1024  # 1MB

    def start(self, container_id):
        response = requests.post(
            f"{self.base_url}/start",
            data=json.dumps({
                "container_id": container_id
            }),
            headers={
                "Content-Type": "application/json"
            }
        )

        try:
            if response.status_code == 200:
                return True

            return False
        except requests.RequestException as e:
            print(e)
            return False

    def upload(self, checkpoint_path, pre=False):
        file_size = os.path.getsize(checkpoint_path)
        headers = {"Filename": os.path.basename(checkpoint_path)}

        with open(checkpoint_path, 'rb') as file:
            start = 0

            chunk_count = math.ceil(float(file_size) / self.chunk_size)
            retry_timeout = 1
            sent_chunk_count = 0

            while True:
                end = min(file_size, start + self.chunk_size)
                headers['Range'] = "bytes={}-{}/{}".format(start, end, file_size)

                file.seek(start)
                data = file.read(self.chunk_size)
                start = end

                upload_endpoint = f"{self.base_url}/upload-{'checkpoint' if not pre else 'pre-checkpoint'}"

                try:
                    response = requests.post(upload_endpoint, headers=headers, data=data)
                    if response.ok:
                        print(f"{round((sent_chunk_count + 1) / chunk_count * 100, 2)}% transfer completed")
                        sent_chunk_count += 1
                except requests.exceptions.RequestException:
                    print('Error while sending chunk to server. Retrying in {} seconds'.format(retry_timeout))
                    time.sleep(retry_timeout)

                    # Sleep for max 10 seconds
                    if retry_timeout < 10:
                        retry_timeout += 1
                    continue

                if sent_chunk_count >= chunk_count:
                    return True

            return False

    def restore(self, container_ip):
        response = requests.post(
            f"{self.base_url}/restore",
            data=json.dumps({
                "container_ip": container_ip
            }),
            headers={
                "Content-Type": "application/json"
            }
        )

        try:
            if response.status_code == 200:
                return True

            return False
        except requests.RequestException as e:
            print(e)
            return False

    def get_ip_data(self):
        response = requests.get(
            f"{self.base_url}/ip_data"
        )

        try:
            if response.status_code == 200:
                return response.content.decode("utf-8").split()
            return []
        except requests.RequestException as e:
            print(e)
            return []

    def pingpong_ip(self):
        response = requests.get(
            f"{self.base_url}/pingpong_ip"
        )

        try:
            if response.status_code == 200:
                return response.content.decode("utf-8")
            return ""
        except requests.RequestException as e:
            print(e)
            return ""

    def teardown_wg(self):
        response = requests.post(
            f"{self.base_url}/teardown_wg"
        )

        try:
            if response.status_code == 200:
                return True
            return False
        except requests.RequestException as e:
            print(e)
            return False

    def wg_setup_initial(self, peer_ip, this_ip):
        response = requests.post(
            f"{self.base_url}/wg_setup_initial",
            data=json.dumps({
                "peer_ip": peer_ip,
                "this_ip": this_ip
            }),
            headers={
                "Content-Type": "application/json"
            }
        )

        try:
            if response.status_code == 200:
                return response.json()

            return {}
        except requests.RequestException as e:
            print(e)
            return {}

    def wg_setup_peer(self, peer_port, peer_pubkey):
        response = requests.post(
            f"{self.base_url}/wg_setup_peer",
            data=json.dumps({
                "peer_port": peer_port,
                "peer_pubkey": peer_pubkey
            }),
            headers={
                "Content-Type": "application/json"
            }
        )

        try:
            if response.status_code == 200:
                return True

            return False
        except requests.RequestException as e:
            print(e)
            return False

    def activate_wg(self):
        response = requests.post(
            f"{self.base_url}/activate_wg"
        )

        try:
            if response.status_code == 200:
                return True

            return False
        except requests.RequestException as e:
            print(e)
            return False

    def activate_migration_routing(self):
        response = requests.post(
            f"{self.base_url}/activate_migration_routing"
        )

        try:
            if response.status_code == 200:
                return True

            return False
        except requests.RequestException as e:
            print(e)
            return False

    def verify_wg(self):
        response = requests.get(
            f"{self.base_url}/verify_wg"
        )

        try:
            if response.status_code == 200:
                return int(response.content.decode("utf-8")) == 1

            return False
        except requests.RequestException as e:
            print(e)
            return False


    def complete(self):
        response = requests.post(
            f"{self.base_url}/complete"
        )
