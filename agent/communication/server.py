import grpc.aio

class SocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server = None


    def construct(self):
        server = grpc.aio.server()
        server.add_insecure_port(f"{self.host}:{self.port}")

        self.server = server

        return self

    async def listen(self):
        await self.server.start()
        await self.server.wait_for_termination()

        return self
