from qns.network.network import QuantumNetwork
from threshold_bb84 import BB84RecvApp, BB84SendApp
from routing_packet import SendRoutingApp, RecvRoutingApp, start_time_order, c_length, q_length, light_speed
from qns.entity.cchannel.cchannel import ClassicChannel
from qns.entity.node.node import QNode
from qns.simulator.simulator import Simulator
from waxman_model import WaxmanTopology
from qns.network.topology.topo import ClassicTopology
from qns.network.route import DijkstraRouteAlgorithm
from create_request_ton import random_requests
from create_request_ton import time_accuracy as accuracy
from qns.utils import set_seed
import numpy as np
#   import matplotlib
import matplotlib.pyplot as plt
#   from matplotlib import style
#   matplotlib.use('TkAgg')

#   matplotlib.rcParams['text.usetex'] = True  # 开启Latex风格
#   plt.figure(figsize=(10, 10), dpi=70)  # 设置图像大小


def drop_rate(length):   # 0.2db/km
    return 1-np.power(10, -length/50000)


end_simu_time = 100
send_rate = 30
s_time = 0
e_time = end_simu_time / 10 * 9
s_request = 10
e_request = 500
s_delay = 10
e_delay = end_simu_time     # float('inf')
square_size = 10000

set_seed(1641801012)


def calculate_consume_key(nodes: list[QNode]):
    consume_key = 0
    for node in nodes:
        sendapp = node.get_apps(SendRoutingApp).pop(0)
        consume_key += sendapp.consume_key
    return consume_key


end_to_end_key_rate_list = []
succ_serve_rate_list = []
consume_key_list = []
request_num_list = []
node_num_list = []
for node_num in [20]:   # , 100, 150, 200, 250
    for i in range(1, 21):
        request_num = int(i * node_num)
        s = Simulator(0, end_simu_time, accuracy)
        topo = WaxmanTopology(nodes_number=node_num, size=square_size, alpha=1, beta=1, qchannel_args={"delay": q_length / light_speed, "drop_rate": drop_rate(q_length)},
                              cchannel_args={"delay": c_length / light_speed})
        #   , lines_number=math.floor(node_num**2/4)
        net = QuantumNetwork(topo=topo, route=DijkstraRouteAlgorithm(), classic_topo=ClassicTopology.All)
        #   print(net.qchannels)
        request_management = {}
        # 初始化，所有节点维护的拓扑一致
        net_bb84rapps = {}
        net_bb84sapps = {}
        net_succ_request = {}
        net_fail_request = {}
        net_link_value = {}     # greedy uses this
        net_restrict = {}   # write down the unavailable link to make the selection reliable
        net_reject_app_packet_symbol = {}
        routing_info = {}
        net_send_mode = {}
        sendlist = []
        recvlist = []
        for node in net.nodes:
            net_bb84sapps[node.name] = []
            net_bb84rapps[node.name] = []
            net_succ_request[node.name] = []
            net_fail_request[node.name] = []
            net_restrict[node.name] = {}
            net_reject_app_packet_symbol[node.name] = {}
            routing_info[node.name] = {}
            net_link_value[node.name] = {}
            net_send_mode[node.name] = {}
            for q in node.qchannels:
                node_list = q.node_list
                if node_list[0] == node:
                    temp = node_list[1]
                else:
                    temp = node_list[0]
                net_restrict[node.name][temp.name] = {}
            for n in net.nodes:
                routing_info[node.name][n.name] = {}  # initialize routing table
        for qchannel in net.qchannels:
            (src, dest) = qchannel.node_list
            cchannel: ClassicChannel = src.get_cchannel(dest)
            send = BB84SendApp(dest=dest, qchannel=qchannel, cchannel=cchannel, send_rate=send_rate)
            recv = BB84RecvApp(src=src, qchannel=qchannel, cchannel=cchannel)
            sendlist.append(send)
            recvlist.append(recv)
            src.add_apps(send)
            dest.add_apps(recv)
            net_bb84sapps[src.name].append(send)
            net_bb84sapps[dest.name].append(send)
            net_bb84rapps[src.name].append(recv)
            net_bb84rapps[dest.name].append(recv)
        net.build_route()
        random_requests(nodes=net.nodes, number=request_num, start_time=s_time, end_time=e_time, start_request=s_request,
                        end_request=e_request, start_delay=s_delay, end_delay=e_delay, allow_overlay=True)

        # print(net.requests)

        for node in net.nodes:
            start_time_order(node.requests, 0, len(node.requests)-1)
            sendre = SendRoutingApp(net=net, node=node, topo=topo, send_mode=net_send_mode[node.name], restrict=net_restrict[node.name], reject_app_packet_symbol=net_reject_app_packet_symbol[node.name], link_value=net_link_value[node.name],
                                    bb84_sapps=net_bb84sapps[node.name], bb84_rapps=net_bb84rapps[node.name], request_management=request_management, routing_info=routing_info[node.name])
            recvre = RecvRoutingApp(net=net, node=node, topo=topo, send_mode=net_send_mode[node.name], restrict=net_restrict[node.name], reject_app_packet_symbol=net_reject_app_packet_symbol[node.name],
                                    link_value=net_link_value[node.name], bb84_sapps=net_bb84sapps[node.name], bb84_rapps=net_bb84rapps[node.name], request_management=request_management,
                                    succ_request=net_succ_request[node.name], fail_request=net_fail_request[node.name], routing_info=routing_info[node.name])
            node.add_apps(sendre)
            node.add_apps(recvre)
        net.install(s)
        #   print(net.qchannels)
        s.run()
        request_num_list.append(request_num)
        node_num_list.append(node_num)
        succ_num = 0
        end_to_end_key = 0
        for node in net.nodes:
            succ_num += len(net_succ_request[node.name])
            for re in net_succ_request[node.name]:
                end_to_end_key += re.attr["key requirement"]
        #   succ_num = calculate_request_serve_rate(net.nodes)  # 计算请求服务率
        succ_serve_rate_list.append(succ_num / request_num)
        consume_key = calculate_consume_key(net.nodes)  # 传到一半失败的包会消耗一定密钥
        consume_key_list.append(consume_key)
        end_to_end_key_rate_list.append(end_to_end_key / consume_key)
    plt.xticks(np.arange(0, 420, 20))
    plt.xlabel('request number')
    plt.ylim((0, 1.1))
    #   plt.ylabel('rate of serving successfully')
    plt.yticks(np.arange(0, 1.1, 0.1))
    plt.plot(request_num_list, succ_serve_rate_list, color='grey',
             marker='o', markersize=6, linewidth=2, markerfacecolor='gray',
             markeredgecolor='grey', markeredgewidth=2)
    plt.plot(request_num_list, end_to_end_key_rate_list, color='red',
             marker='o', markersize=6, linewidth=2, markerfacecolor='red',
             markeredgecolor='red', markeredgewidth=2)
    plt.legend(['rate of serving successfully', 'rate of consuming keys'], loc='upper right')
    # plt.plot(request_num_list, consume_key_list, color='blue',
    #          marker='o', markersize=6, linewidth=2, markerfacecolor='blue',
    #          markeredgecolor='blue', markeredgewidth=2)
    # plt.legend(['number of consumed keys'], loc='upper left')
    plt.show()
