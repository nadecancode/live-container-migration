import grpc


class SocketClient:
    def __init__(self, host, port):
        self.channel = None
        self.host = host
        self.port = port

    async def connect(self):
        self.channel = grpc.aio.insecure_channel(f"{self.host}:{self.port}")

        return self.channel
