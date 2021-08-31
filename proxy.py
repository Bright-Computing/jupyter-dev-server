#!/usr/bin/env python3
import os
import select
import socket
import ssl
import sys
import time

# LOCAL HOST OPTIONS
JUPYTER_PROXY_IP_OR_NAME = os.getenv('JUPYTER_PROXY_IP_OR_NAME', 'localhost')
JUPYTER_PROXY_PORT = int(os.getenv('JUPYTER_PROXY_PORT', 8000))

# REMOTE HOST OPTIONS
JUPYTER_SERVER_IP_OR_NAME = os.getenv('JUPYTER_SERVER_IP_OR_NAME', '1.2.3.4')
JUPYTER_SERVER_PORT = int(os.getenv('JUPYTER_SERVER_PORT', 8000))
JUPYTER_SERVER_NAME = os.getenv('JUPYTER_SERVER_NAME', 'jupyterhub')  # name used to verify connection via SSL
# ref: cmsh -c "configurationoverlay; use jupyterhub; roles; use jupyterhub; show" | grep domains
JUPYTER_USERNAME = os.getenv('JUPYTER_USERNAME', 'myusername')
JUPYTER_CLUSTER_CA_CERT = os.getenv('JUPYTER_CLUSTER_CA_CERT', "./my_sslca.cert")
# ref: /cm/local/apps/jupyter/current/conf/certs/

# CONNECTION OPTIONS
BUFFER_SIZE = 2 ** 14  # increase this value with caution
SLEEP_DELAY = 0.0001  # decrease this value with caution
SERVER_SOCKET_BACKLOG = 200
# ref: https://docs.python.org/3/library/socket.html#socket.socket.listen


class JupyterDevServer:

    def __init__(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        self.open_sockets = []
        self.channel = {}
        self.ssl_context = None

    def __enter__(self):
        self.server_socket.bind((JUPYTER_PROXY_IP_OR_NAME, JUPYTER_PROXY_PORT))
        self.server_socket.listen(SERVER_SOCKET_BACKLOG)
        self.open_sockets.append(self.server_socket)
        self.ssl_context = ssl.create_default_context(
            cafile=JUPYTER_CLUSTER_CA_CERT,
        )
        print(f"Server running at: http://{JUPYTER_PROXY_IP_OR_NAME}:{JUPYTER_PROXY_PORT}")
        print(f"Forwarding requests to: http://{JUPYTER_SERVER_IP_OR_NAME}:{JUPYTER_SERVER_PORT}\n")
        print(f"Jupyter username: {JUPYTER_USERNAME}")
        print(f"CA certificate file: {JUPYTER_CLUSTER_CA_CERT}")
        print(f"Jupyter authorized server name: {JUPYTER_SERVER_NAME}\n")
        print(f"Authorization URL with token for IDE: http://{JUPYTER_PROXY_IP_OR_NAME}:{JUPYTER_PROXY_PORT}/?token=<YOUR_API_TOKEN>\n")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.server_socket.close()

    def forward_requests(self):
        while True:
            read_ready_sockets, _, _ = select.select(self.open_sockets, [], [])
            for ready_socket in read_ready_sockets:
                if ready_socket == self.server_socket:
                    self.on_accept()
                    break
                try:
                    data = ready_socket.recv(BUFFER_SIZE)
                    if len(data) == 0:
                        self.on_close(ready_socket)
                        break
                    self.on_receive(ready_socket, data)
                except ConnectionError as exc:
                    print(exc)
                    print("Can't establish connection with remote server.")
            time.sleep(SLEEP_DELAY)

    def on_accept(self):
        # try to establish connection with remote Jupyter server
        forward_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        forward_socket = self.ssl_context.wrap_socket(
            forward_socket,
            server_hostname=JUPYTER_SERVER_NAME,
        )
        client_socket, client_address = None, None
        try:
            forward_socket.connect(
                (JUPYTER_SERVER_IP_OR_NAME, JUPYTER_SERVER_PORT),
            )
            client_socket, client_address = self.server_socket.accept()
            print(client_address, "has connected")
            self.open_sockets.append(client_socket)
            self.open_sockets.append(forward_socket)
            self.channel[client_socket] = forward_socket
            self.channel[forward_socket] = client_socket
        except ssl.CertificateError:
            print(
                "Can't establish connection with remote server. "
                "Incorrect CA certificates."
            )
            raise
        except ConnectionError as exc:
            print(exc)
            print("Can't establish connection with remote server.")
            if client_socket and client_address:
                print("Closing connection with client side", client_address)
                client_socket.close()

    def on_close(self, client_socket):
        try:
            print(client_socket.getpeername(), "has disconnected")
            # close sockets and cleanup channel dict
            self.open_sockets.remove(client_socket)
            self.open_sockets.remove(self.channel[client_socket])
            forward_socket = self.channel[client_socket]
            self.channel[forward_socket].close()
            self.channel[client_socket].close()
            del self.channel[forward_socket]
            del self.channel[client_socket]
        except OSError as exc:
            print(exc)
            print("Can't close connection with client.")

    def on_receive(self, client_socket, data):
        data = redirect_requests_to_hub(data)
        self.channel[client_socket].send(data)


def redirect_requests_to_hub(data):
    encoding = 'utf-8'
    jupyter_api_endpoint = ' /api/'
    hub_api_endpoint = f" /user/{JUPYTER_USERNAME}/api/"
    try:
        data = data.decode(encoding)
        lines = data.split('\n')
        if jupyter_api_endpoint in lines[0]:
            print(
                f"Rewriting '{jupyter_api_endpoint}' request to "
                f"'{hub_api_endpoint}'"
            )
            lines[0] = lines[0].replace(jupyter_api_endpoint, hub_api_endpoint)
        return '\n'.join(lines).encode(encoding)
    except UnicodeDecodeError:  # ignore non-plain text packets
        return data


def main():
    try:
        with JupyterDevServer() as dev_server:
            dev_server.forward_requests()
    except KeyboardInterrupt:
        print("Ctrl C - Stopping JupyterDevServer")
        sys.exit(1)


if __name__ == '__main__':
    main()
