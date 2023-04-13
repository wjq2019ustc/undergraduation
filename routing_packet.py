from qns.entity.node.app import Application
from qns.network.requests import Request


class SendRoutingApp(Application):
    def __init__(self, request_list: list[Request] = []):
        super().__init__()


class RecvRoutingApp(Application):
    def __init__(self, request_list: list[Request] = []):
        super().__init__()
