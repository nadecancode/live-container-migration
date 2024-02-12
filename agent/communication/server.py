import grpc.aio

class SocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server = None


    async def listen(self):
        server = grpc.aio.server()

        server.add_insecure_port(f"{self.host}:{self.port}")
        await server.start()

        await server.wait_for_termination()

        self.server = server
        return self.server
