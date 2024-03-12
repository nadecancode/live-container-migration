import time
import os
import socket
import atexit

host = os.environ["DESTINATION_HOST"]
port = os.environ["DESTINATION_PORT"]

i = 0

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # TCP_NODELAY, we want packets IMMEDIATELY
s.connect((host, port))

atexit.register(lambda _: s.close())

while True:
    print(f"Sending number {i} to {host}:{port}")
    i += 1

    time.sleep(1)