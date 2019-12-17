from socket import socket
from socket import error
from socket import AF_INET
from socket import SOCK_STREAM
from socket import SOCK_DGRAM
from socket import SHUT_RDWR
from socket import SHUT_WR
from threading import Thread
from threading import Lock
from weights import get_new_weight

class defaultdict(dict):
    def __init__(self, default_factory=None, *a, **kw):
        if (default_factory is not None and
                not hasattr(default_factory, '__call__')):
            raise TypeError('first argument must be callable')
        dict.__init__(self, *a, **kw)
        self.default_factory = default_factory

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return self.__missing__(key)

    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        self[key] = value = self.default_factory()
        return value

    def __reduce__(self):
        if self.default_factory is None:
            args = tuple()
        else:
            args = self.default_factory,
        return type(self), args, None, None, self.items()

    def copy(self):
        return self.__copy__()

    def __copy__(self):
        return type(self)(self.default_factory, self)

    def __deepcopy__(self, memo):
        import copy
        return type(self)(self.default_factory,
                          copy.deepcopy(self.items()))

    def __repr__(self):
        return 'defaultdict(%s, %s)' % (self.default_factory,
                                        dict.__repr__(self))

class Graph():
    def __init__(self):
        """
        self.edges is a dict of all possible next nodes
        e.g. {'X': ['A', 'B', 'C', 'E'], ...}
        self.weights has all the weights between two nodes,
        with the two nodes as a tuple as the key
        e.g. {('X', 'A'): 7, ('X', 'B'): 2, ...}
        """
        self.edges = defaultdict(list)
        self.weights = {}

    def add_edge(self, from_node, to_node, weight):
        # Note: assumes edges are bi-directional
        if to_node not in self.edges[from_node]:
            self.edges[from_node].append(to_node)
        #self.edges[to_node].append(from_node)
        self.weights[(from_node, to_node)] = weight
        #self.weights[(to_node, from_node)] = weight

    def get_edge(self, from_node, to_node):
        # Note: assumes edges are bi-directional
        return int(self.weights[(from_node, to_node)])

def router(my_name):
    udp_file = "UDP_output_router_" + str(my_name) + ".txt"
    file = open(udp_file, 'w')
    file.close()
    tcp_file = "TCP_output_router_" + str(my_name) + ".txt"
    file = open(tcp_file, 'w')
    file.close()
    file = open("input_router_" + str(my_name) + ".txt", 'r')
    data = file.read().split('\n')
    file.close()
    ip = "127.0.0.1"
    udp_port = int(data[0])
    tcp_port = int(data[1])
    num_of_routers = int(data[2])
    neighbors = []
    index = 3
    first_neighbor = data[index]
    lv={}
    msg_box=[]
    round=1
    i = 0
    while data[index] != '*':
        neighbors.append({})
        neighbors[i]['Name'] = data[index]
        neighbors[i]['ip'] = data[index + 1]
        neighbors[i]['UDP_port'] = data[index + 2]
        neighbors[i]['TCP_port'] = data[index + 3]
        neighbors[i]['edge_weight'] = data[index + 4]
        lv[my_name,int(data[index])]= int(data[index+4])
        index = index + 5
        i += 1
    num_of_neighbors=int(len(neighbors))
    diameter = data[index + 1]
    routing_table=init_routing_table(my_name,num_of_routers,first_neighbor,diameter)
    lv,neighbors = init_packet(neighbors,my_name,lv,round)

    Thread(target=tcp_listen, args=(my_name,tcp_port, ip , neighbors,msg_box,tcp_file)).start()
    Thread(target=udp_listen, args=(my_name,udp_port,tcp_port, ip,num_of_routers,routing_table,neighbors,msg_box,lv,tcp_file,udp_file)).start()



def init_routing_table(my_name, num_of_routers,first_neighbor, diameter):
    routing_table = {}
    for i in range(1, int(num_of_routers) + 1):
        if i != my_name:
            routing_table[i] = {}
            routing_table[i]['dist'] = int(diameter)
            routing_table[i]['next'] = first_neighbor
        else:
            routing_table[i] = {}
            routing_table[i]['dist'] = 0
            routing_table[i]['next'] = None

    return routing_table

def init_packet(neighbors,my_name,lv,round):
    for i in range(len(neighbors)):
        lv[(my_name, int(neighbors[i]['Name']))] = int(neighbors[i]['edge_weight'])
        new_weight = get_new_weight(my_name, round, i , len(neighbors))
        if new_weight is not None:
            neighbors[i]['edge_weight']=new_weight
            lv[(my_name, int(neighbors[i]['Name']))] = int(neighbors[i]['edge_weight'])
    return lv,neighbors

def udp_listen(my_name,udp_port, tcp_port,ip, num_of_routers,routing_table,neighbors,msg_box,lv,tcp_file,udp_file):
    round=2

    udp_server_socket = socket(AF_INET, SOCK_DGRAM)
    udp_server_socket.bind((ip, udp_port))
    flag=True
    while flag:
        data, addr=udp_server_socket.recvfrom(4096)
        udp_data = data.decode()
        if udp_data == 'SHUT-DOWN':
            flag = False
            args = [ip,tcp_port, "SHUT-DOWN"]
            tcp_thread_terminate = Thread(target=shut_down_tcp, args=tuple(args))
            tcp_thread_terminate.start()
            tcp_thread_terminate.join()
            udp_server_socket.close()
            try:
                udp_server_socket.shutdown(SHUT_RDWR)
            except OSError:
                pass

        elif udp_data=='UPDATE-ROUTING-TABLE':
            args = [my_name,round, routing_table, neighbors,num_of_routers,msg_box,lv,tcp_file,addr[1]]
            Thread(target=update_routing_table, args=tuple(args)).start()
            round+=1

        elif "ROUTE" in udp_data:
            args=[my_name, udp_data, routing_table,neighbors,udp_file]
            Thread(target=route, args=tuple(args)).start()

        elif udp_data=='PRINT-ROUTING-TABLE':
            args=[routing_table,udp_file]
            Thread(target=print_routing_table, args=tuple(args)).start()

def shut_down_tcp(ip,tcp_port,msg):
    sock_tcp=socket(AF_INET,SOCK_STREAM)
    sock_tcp.connect((ip,int(tcp_port)))
    sock_tcp.sendto(msg.encode(), (ip, int(tcp_port)))
    sock_tcp.close()

def update_routing_table(my_name,round, routing_table, neighbors,num_of_routers,msg_box,lv,tcp_file,addr):
    msg_box.clear()
    threads=[]
    for i in range(1,(len(neighbors)+1)):
        message = str(round)+ ';' + str(my_name) + ';' + str(i) + ';' + str(lv)
        thread1=Thread(target=send_to_neighbors,args=(my_name,message,neighbors,msg_box,tcp_file))
        threads.append(thread1)

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    flag=True
    while flag:
        if (len(msg_box) == (num_of_routers)):
            flag=False

    graph=Graph()
    for i in msg_box:
        for j in i:
            graph.add_edge(str(j[0]),str(j[1]),i[j])

    change_table(graph,num_of_routers,my_name,routing_table)
    init_packet(neighbors,my_name,lv,round)
    Thread(target=send_udp(addr, 'FINISHED')).start()

def send_udp(port, message):
    ip = '127.0.0.1'
    udp_sock = socket(AF_INET, SOCK_DGRAM)
    udp_sock.sendto(message.encode(), (ip, int(port)))

def change_table(graph, num_of_routers, my_name, routing_table):
    i = 1
    while i <= num_of_routers:
        if i != my_name:
            path = dijsktra(graph, str(my_name), str(i))
            routing_table[i]['next'] = path[1]
            dist = 0
            j = 0
            while j < len(path) - 1:
                dist = dist + graph.get_edge(path[j], path[j + 1])
                j += 1
            routing_table[i]['dist'] = dist
        i += 1

def tcp_listen(my_name,tcp_port,ip, neighbors,msg_box,tcp_file):
    tcp_socket = socket(AF_INET, SOCK_STREAM)
    tcp_socket.bind((ip,tcp_port))
    tcp_socket.listen(999999999)
    while 1:
        conn, addr = tcp_socket.accept()
        r_data=conn.recv(4096)
        data=r_data.decode()

        if "SHUT-DOWN" in data:
            tcp_socket.close()
            break

        else:
            thread = Thread(target=send_to_neighbors, args=(my_name, data, neighbors, msg_box, tcp_file))
            thread.start()
            thread.join()

    tcp_socket.close()

def send_to_neighbors(my_name,message,neighbors,msg_box,tcp_file):
    port=0
    lock=Lock()
    round=int(message.split(';')[0])
    sou=int(message.split(';')[1])
    adj=eval(message.split(';')[3])
    lock.acquire()
    if adj not in msg_box:
        msg_box.append(adj)
        lock.release()
        for n in neighbors:
            if str(sou) != n['Name']:
                port = int(n['TCP_port'])
                lock.acquire()
                string_to_print='UPDATE;'+str(my_name)+';'+str(n['Name'])+'\n'
                file = open(tcp_file, "a")
                file.write(string_to_print)
                lock.release()
                thread = Thread(target=tcp_keep_send(my_name,str(n['Name']),port, message,tcp_file))
                thread.start()
                thread.join()


def tcp_keep_send(my_name,to_who,tcp_port,tcp_data,tcp_file):
    ip = "127.0.0.1"
    tcp_socket=socket(AF_INET, SOCK_STREAM)
    data = str(tcp_data)
    while True:
        try:
            tcp_socket.connect(((ip, int(tcp_port))))
            tcp_socket.send(data.encode())
            break
        except:
            pass
    #tcp_socket.close()

def route(name,message,routing_table,neighbors,udp_file):
    lock=Lock()
    dest=int(message.split(';')[1])
    lock.acquire()
    file = open(udp_file, "a")
    file.write(message + '\n')
    file.close()
    lock.release()
    if dest!=name:
        to_who=routing_table[int(dest)]['next']
        for n in neighbors:
            if str(to_who)==n['Name']:
                port=int(n['UDP_port'])
                Thread(target=send_udp(port,message)).start()

def print_routing_table(routing_table,udp_file):
    lock=Lock()
    string_to_print = ""
    for router in routing_table:
        string_to_print = string_to_print + str(routing_table[router]['dist']) + ";" + str(routing_table[router]['next']) + "\n"
    lock.acquire()
    file = open(udp_file, 'a')
    file.write(string_to_print)
    lock.release()
    file.close()

def dijsktra(graph, initial, end):
    # shortest paths is a dict of nodes
    # whose value is a tuple of (previous node, weight)
    shortest_paths = {initial: (None, 0)}
    current_node = initial
    visited = set()

    while current_node != end:
        visited.add(current_node)
        destinations = graph.edges[current_node]
        weight_to_current_node = shortest_paths[current_node][1]

        for next_node in destinations:
            weight = graph.weights[(current_node, next_node)] + weight_to_current_node
            if next_node not in shortest_paths:
                shortest_paths[next_node] = (current_node, weight)
            else:
                current_shortest_weight = shortest_paths[next_node][1]
                if current_shortest_weight > weight:
                    shortest_paths[next_node] = (current_node, weight)

        next_destinations = {node: shortest_paths[node] for node in shortest_paths if node not in visited}
        if not next_destinations:
            return "Route Not Possible"
        # next node is the destination with the lowest weight
        current_node = min(next_destinations, key=lambda k: next_destinations[k][1])

    # Work back through destinations in shortest path
    path = []
    while current_node is not None:
        path.append(current_node)
        next_node = shortest_paths[current_node][0]
        current_node = next_node
    # Reverse path
    path = path[::-1]
    return path
