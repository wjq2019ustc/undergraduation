from qns.entity.node.app import Application
from qns.network.requests import Request
from qns.entity.node.node import QNode
from qns.simulator.simulator import Simulator
from qns.simulator.event import func_to_event, Event
from qns.entity.cchannel.cchannel import ClassicChannel, ClassicPacket, RecvClassicPacket
from qns.entity.qchannel.qchannel import QuantumChannel
from threshold_bb84 import BB84RecvApp, BB84SendApp
import math

packet_length = 20


def start_time_order(re_list: list[Request], s: int, e: int):
    if s >= e:
        return
    val = re_list[e].attr["start time"]
    left = s
    right = e
    while left < right:
        while re_list[left].attr["start time"] < val and left < right:
            left += 1
        while re_list[right].attr["start time"] >= val and left < right:
            right -= 1
        if left < right:
            temp = re_list[left]
            re_list[left] = re_list[right]
            re_list[right] = temp
    if re_list[left].attr["start time"] < val:
        left += 1
    temp = re_list[left]
    re_list[left] = re_list[e]
    re_list[e] = temp
    start_time_order(re_list, s, left-1)
    start_time_order(re_list, left+1, e)


def create_request_info(request_management: dict, sym: str, re: Request):
    request_management[sym] = {}
    request_management[sym]["dest"] = re.dest
    request_management[sym]["src"] = re.src
    request_management[sym]["attr"] = re.attr
    request_management[sym]["state"] = "finding"
    #   routing/successful/failed                      /rerouting/refinding
    request_management[sym]["request times"] = 1
    request_management[sym]["start routing"] = 0
    #   the time when first application packet is sent by src
    request_management[sym]["end routing"] = 0
    #   the time when last application packet is received by dest
    request_management[sym]["packet arrival"] = {}
    request_management[sym]["packet number"] = math.ceil(re.attr["key requirement"] / packet_length)
    #   for i in range(math.ceil(re.attr["key requirement"] / packet_length)):
    #       request_management[sym]["packet arrival"][i] = False

def search_app(sapps: list[BB84SendApp], rapps: list[BB84RecvApp], qchannel_name: str = ""):   # 得到qchannel对应的bb84app
    temps = None
    tempr = None
    for app in sapps:
        if app.qchannel.name == qchannel_name:
            temps = app
            break
    for app in rapps:
        if app.qchannel.name == qchannel_name:
            tempr = app
            break
    return temps, tempr

def search_next_hop(msg: str):
    pass


class SendRoutingApp(Application):
    def __init__(self, bb84_sapps: list[BB84SendApp], bb84_rapps: list[BB84RecvApp], fail_request: list[Request] = [], request_management: dict = {}, routing_info: dict = {}):
        # 以请求为单位进行管理， 以目的节点为索引进行寻路
        super().__init__()
        node: QNode = self.get_node()
        self.request_list = node.requests
        self.request_management = request_management
        self.fail_request = fail_request
        self.routing_table = routing_info
        self.count = 0

    def install(self, node: QNode, simulator: Simulator):
        super().install(node, simulator)
        self._simulator = simulator
        self._node = node
        if len(self.request_list) > 0:
            re = self.request_list.pop(0)
            temp = re.attr["start time"]
            t = temp+simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_re_packet, re=re, first_flag = True)
            self._simulator.add_event(event)

    def send_re_packet(self, re: Request, first_flag: bool):
        if len(self.request_list) > 0:
            r = self.request_list.pop(0)
            temp = r.attr["start time"]
            t = temp+self._simulator.ts
            # print(re.attr, t)
            event = func_to_event(t, self.send_re_packet, re=r, first_flag=True)
            self._simulator.add_event(event)
        src = re.src
        dest = re.dest
        attr = re.attr
        if first_flag:  # 第一次路由
            symbol = f"{self._node.name}-{self.count}"
            self.count += 1
            create_request_info(self.request_management, symbol, re)
        msg = {"symbol": symbol, "type": "finding", "mode": "greedy", "loop": 0, "RecPosition": None, "RecIF": None,
               "src": src, "dest": dest, "key requirement": attr["key requirement"], "request times": self.request_management[symbol]["request times"]}
        #   一开始是贪婪模式，不存在恢复模式需要的信息
        next_hop = search_next_hop(msg)
        self.routing_table[dest.name][symbol] = next_hop
        cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
        packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
        cchannel.send(packet=packet, next_hop=next_hop)

    #   def resend_re_packet(symbol: str):

    def send_app_packet(self, info: dict, order: int, data_packet_length: int = 0):
        #   length stands for single key requirement
        sym = info["symbol"]
        dest = info["dest"]
        msg = {"symbol": sym, "type": "routing", "src": info["src"], "dest": dest, "order": order, "length": data_packet_length,
               "start time": self.request_management[sym]["start routing"], "delay": info["delay"]}
        next_hop = self.routing_table[dest.name][sym]
        cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
        packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
        cchannel.send(packet=packet, next_hop=next_hop)


class RecvRoutingApp(Application):
    def __init__(self, node: QNode, bb84_sapps: list[BB84SendApp], bb84_rapps: list[BB84RecvApp], request_management: dict = {}, succ_request: list = [], routing_info: dict = {}):
        super().__init__()
        self.routing_table = routing_info
        self.request_management = request_management
        self.success_request = succ_request
        self.bb84_sapps = bb84_sapps
        self.bb84_rapps = bb84_rapps
        self.waiting_queue: list = []

    def install(self, node, simulator: Simulator):
        super().install(node, simulator)
        self._simulator = simulator
        self._node = node
        self.add_handler(self.handleClassicPacket, [RecvClassicPacket], [])

    def handleClassicPacket(self, node, event: Event):
        if isinstance(event, RecvClassicPacket):
            packet_time = event.t
            packet = event.packet
            # get the packet message
            msg = packet.get()
            msg_type = msg["type"]
            symbol = msg["symbol"]
            dest = msg["dest"]
            src = msg["src"]
            if msg_type == "finding":
                if dest == self._node:
                    answer:dict = {"symbol": symbol, "type": "finding answer", "src": src, "dest": dest, "answer": "yes"}
                else:
                    mode = msg["mode"]
                    msg = {"symbol": symbol, "type": "finding", "mode": "greedy", "loop": 0, "RecPosition": None, "RecIF": None,
                    "src": src, "dest": dest, "key requirement": attr["key requirement"], "request times": self.request_management[symbol]["request times"]}
                    #   一开始是贪婪模式，不存在恢复模式需要的信息
                    next_hop = search_next_hop(msg)
                    self.routing_table[dest.name][symbol] = next_hop
                    cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                    packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
                    cchannel.send(packet=packet, next_hop=next_hop)





            elif msg_type == "finding answer":
                if self.request_management[symbol]["state"] == "finding":
                    answer = msg["answer"]
                    if answer == "yes": # 寻路成功(dest send)即发包
                        packet_src = packet.src
                        if packet_src == dest:
                            key_requirement = self.request_management[symbol]["attr"].get("key requirement")
                            self.request_management[symbol]["state"] = "routing"
                            tc_slot = self._simulator.tc.time_slot
                            self.request_management[symbol]["start routing"] = tc_slot
                            order = 0
                            info: dict = {}
                            info["symbol"] = symbol
                            info["src"] = src
                            info["dest"] = dest
                            info["delay"] = self.request_management[symbol]["attr"].get("delay")
                            sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                            while key_requirement > 0:  # 发送数据包
                                order += 1
                                if key_requirement >= packet_length:
                                    event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=packet_length)   # , None, None
                                    key_requirement -= packet_length
                                else: 
                                    event = func_to_event(self._simulator.tc, sendapp.send_app_packet, info=info, order=order, data_packet_length=key_requirement)
                                    key_requirement = 0
                                self._simulator.add_event(event)
                    elif answer == "no":    # 重新路由
                        self.request_management[symbol]["request times"] += 1
                        attr = self.request_management[symbol]["attr"]
                        re = Request(src=src, dest=dest, attr=attr)
                        sendapp = self._node.get_apps(SendRoutingApp).pop(0)
                        event = func_to_event(self._simulator.tc, sendapp.send_re_packet, re=re, first_flag=False)
                        self._simulator.add_event(event)
            #   elif msg_type == "refinding":
            #   elif msg_type == "refinding answer":
            elif msg_type == "routing":
                order = msg["order"]
                if dest == self._node:  # 给源端反馈
                    answer:dict = {"symbol": symbol, "type": "routing answer", "src": src, "dest": dest, "answer": "yes", "order": order}
                    next_hop = src
                    cchannel: ClassicChannel = self._node.get_cchannel(next_hop)
                    packet = ClassicPacket(msg=msg, src=self._node, dest=next_hop)
                    cchannel.send(packet=packet, next_hop=next_hop)
                else:
                    length = msg["length"]
                    next_hop = self.routing_table[dest.name][symbol]
                    qchannel: QuantumChannel = self._node.get_qchannel(next_hop)
                    sendbb84, recvbb84 = search_app(self.bb84_sapps, self.bb84_rapps, qchannel.name)








            elif msg_type == "routing answer":  # is sent by dest
                if self.request_management[symbol]["state"] == "routing":
                    order = msg["order"]
                    if self.request_management[symbol]["packet arrival"].get(order) is None:
                        answer = msg["answer"]
                        if answer == "yes":
                            self.request_management[symbol]["packet arrival"][order] = True
                            if len(self.request_management[symbol]["packet arrival"]) == self.request_management[symbol]["packet number"]:
                                self.request_management[symbol]["end routing"] = packet_time.time_slot
                                self.request_management[symbol]["state"] = "successful"
                                attr: dict = self.request_management[symbol]["attr"]
                                re = Request(src=src, dest=dest, attr=attr)
                                self.success_request.append(re)
                        elif answer == "no":
                            self.request_management[symbol]["state"] = "failed"
