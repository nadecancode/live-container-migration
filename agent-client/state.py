from enum import Enum

class AgentPeer:
    def __init__(self, host, port):
        self.host = host
        self.port = port


class AgentStatus(Enum):
    IDLE = 1
    CONNECTED = 2
    TRANSPORTING_INITIAL_CHECKPOINT = 3
    TRANSPORTING_LEFT_OVER = 4
    COMPLETED = 5
    DUMPING_CHECKPOINT = 6


class AgentState:
    def __init__(self):
        self.status = AgentStatus.IDLE
        self.progress = 0

        self.peer = None
        self.pin = None
