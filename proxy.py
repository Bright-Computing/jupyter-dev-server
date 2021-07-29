#!/usr/bin/env python3
import select
import socket
import ssl
import sys
import time

# LOCAL HOST OPTIONS
JUPYTER_PROXY_IP_OR_NAME = 'localhost'
JUPYTER_PROXY_PORT = 8000

# REMOTE HOST OPTIONS
JUPYTER_SERVER_IP_OR_NAME = '10.2.76.1'
JUPYTER_SERVER_PORT = 8000
JUPYTER_SERVER_NAME = 'jupyterhub'  # name used to verify connection via SSL
# ref: cmsh -c "configurationoverlay; use jupyterhub; roles; use jupyterhub; show" | grep domains
JUPYTER_USERNAME = 'gianvito'
JUPYTER_CLUSTER_CA_CERT = "my_sslca.cert"
# ref: /cm/local/apps/jupyter/current/conf/certs/

# CONNECTION OPTIONS
BUFFER_SIZE = 4096  # increase this value with caution
SLEEP_DELAY = 0.0001  # decrease this value with caution

# context = ssl.create_default_context()
context = ssl.create_default_context(cafile=JUPYTER_CLUSTER_CA_CERT)
# context.load_cert_chain("my_ssl.cert", "my_ssl.key")


class Forward:
    def __init__(self):
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.forward = context.wrap_socket(
            self.forward,
            server_hostname=JUPYTER_SERVER_NAME,
        )

    def start(self, host, port):
        try:
            self.forward.connect((host, port))
            return self.forward
        except Exception as e:
            print(e)
            return False


class TheServer:
    input_list = []
    channel = {}

    def __init__(self, host, port):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)

    def main_loop(self):
        self.input_list.append(self.server)
        while True:
            time.sleep(SLEEP_DELAY)
            inputready, outputready, exceptready = select.select(self.input_list, [], [])
            for self.s in inputready:
                if self.s == self.server:
                    self.on_accept()
                    break
                try:
                    self.data = self.s.recv(BUFFER_SIZE)
                    if len(self.data) == 0:
                        self.on_close()
                        break
                    else:
                        self.on_recv()
                except ConnectionResetError:
                    pass

    def on_accept(self):
        forward = Forward().start(JUPYTER_SERVER_IP_OR_NAME, JUPYTER_SERVER_PORT)
        clientsock, clientaddr = self.server.accept()
        if forward:
            print(clientaddr, "has connected")
            self.input_list.append(clientsock)
            self.input_list.append(forward)
            self.channel[clientsock] = forward
            self.channel[forward] = clientsock
        else:
            print("Can't establish connection with remote server.",)
            print("Closing connection with client side", clientaddr)
            clientsock.close()

    def on_close(self):
        try:
            print(self.s.getpeername(), "has disconnected")
        except OSError as exc:
            print(exc)
        # remove objects from input_list
        self.input_list.remove(self.s)
        self.input_list.remove(self.channel[self.s])
        out = self.channel[self.s]
        # close the connection with client
        self.channel[out].close()  # equivalent to do self.s.close()
        # close the connection with remote server
        self.channel[self.s].close()
        # delete both objects from channel dict
        del self.channel[out]
        del self.channel[self.s]

    def on_recv(self):
        data = self.data
        # here we can parse and/or modify the data before send forward
        # print(data)
        data = rewrite(data)
        self.channel[self.s].send(data)


def rewrite(data):
    try:
        data = data.decode('utf-8')
        lines = data.split('\n')
        if ' /api/' in lines[0]:
            print('Rewriting /api/ request')
            lines[0] = lines[0].replace(' /api/', f" /user/{JUPYTER_USERNAME}/api/")
        return '\n'.join(lines).encode('utf-8')
    except UnicodeDecodeError:
        return data


def main():
    server = TheServer(JUPYTER_PROXY_IP_OR_NAME, JUPYTER_PROXY_PORT)
    try:
        server.main_loop()
    except KeyboardInterrupt:
        print("Ctrl C - Stopping server")
        sys.exit(1)


if __name__ == '__main__':
    main()
