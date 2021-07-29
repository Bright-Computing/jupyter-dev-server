#!/usr/bin/python
# This is a simple port-forward / proxy, written using only the default python
# library. If you want to make a suggestion or fix something you can contact-me
# at voorloop_at_gmail.com
# Distributed over IDC(I Don't Care) license
import socket
import select
import time
import ssl
import sys

# Changing the buffer_size and delay, you can improve the speed and bandwidth.
# But when buffer get to high or delay go too down, you can broke things
buffer_size = 4096
delay = 0.0001
forward_to = ('10.2.76.1', 8000)
username = 'gianvito'

# context = ssl.create_default_context()
context = ssl.create_default_context(cafile="my_sslca.cert")
# context.load_cert_chain("my_ssl.cert", "my_ssl.key")


class Forward:
    def __init__(self):
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.forward = context.wrap_socket(
            self.forward,
            server_hostname="gt-pycharm",
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
        # self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server = sock
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)

    def main_loop(self):
        self.input_list.append(self.server)
        while 1:
            time.sleep(delay)
            ss = select.select
            inputready, outputready, exceptready = ss(self.input_list, [], [])
            for self.s in inputready:
                if self.s == self.server:
                    self.on_accept()
                    break

                try:
                    self.data = self.s.recv(buffer_size)
                    if len(self.data) == 0:
                        self.on_close()
                        break
                    else:
                        self.on_recv()
                except ConnectionResetError:
                    pass

    def on_accept(self):
        forward = Forward().start(forward_to[0], forward_to[1])
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
            lines[0] = lines[0].replace(' /api/', f" /user/{username}/api/")
        return '\n'.join(lines).encode('utf-8')
    except UnicodeDecodeError:
        return data


def main():
    server = TheServer('localhost', 8000)
    try:
        server.main_loop()
    except KeyboardInterrupt:
        print("Ctrl C - Stopping server")
        sys.exit(1)


if __name__ == '__main__':
    main()
