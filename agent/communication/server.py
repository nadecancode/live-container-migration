import socket

class SocketServer:
    def __init__(self):
        self.host = None
        self.port = None


    def listen(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.bind(("0.0.0.0", 0))
        sock.listen()

        self.host, self.port = sock.getsockname()