import socket
import atexit
import os

host = os.environ["DESTINATION_HOST"]
port = os.environ["DESTINATION_PORT"]

i = 0

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) # TCP_NODELAY, we want packets IMMEDIATELY
s.connect((host, port))

atexit.register(lambda _: s.close())

sep = "\n"

while True:
    buf = ""
    while sep not in buf:
        buf += s.recv(8)
    num = int(buf)

    print(f"Received {num} from server")