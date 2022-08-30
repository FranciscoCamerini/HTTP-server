import argparse
import os
import socket
import selectors
import types

from functions import handle_request


SEL = selectors.DefaultSelector()


def accept_client(sock):
    connection, address = sock.accept()
    connection.setblocking(False)
    data = types.SimpleNamespace(addr=address, inb=b'', outb=b'')
    events = selectors.EVENT_READ
    SEL.register(connection, events, data=data)


def service_connection(key, mask):
    sock = key.fileobj
    sock.settimeout(2)
    data = key.data

    if mask & selectors.EVENT_READ:
        try:
            recv_data = sock.recv(1024)
        except ConnectionResetError:
            pass
        else:
            if recv_data:
                data.outb += recv_data
                if b'\r\n\r\n' in data.outb:
                    events = selectors.EVENT_WRITE
                    SEL.modify(sock, events, data)

    if mask & selectors.EVENT_WRITE:
        if data.outb:
            request = data.outb.decode()
            headers, generator = handle_request(request)
            sock.sendall(headers)

            for chunk in generator:
                sock.sendall(chunk)
            SEL.unregister(sock)
            sock.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind_address', '-b', action='store', default='0.0.0.0', type=str,
                            nargs='?', help='Specify alternative bind adresss (default: 0.0.0.0)')
    parser.add_argument('port', action='store', default=8888, type=int,
                            nargs='?', help='Specify alternative port (default: 8888)')
    parser.add_argument('--directory', '-d', action='store', default=os.getcwd(), type=str,
                            nargs='?', help='Specify alternative directory inside this folder(default: current directory)')
    args = parser.parse_args()

    server_host = args.bind_address
    server_port = args.port
    start_dir = args.directory
    return server_host, server_port, start_dir


def change_directory(start_dir):
    if start_dir != os.getcwd():
        try:
            os.chdir(os.path.abspath(start_dir))
        except FileNotFoundError:
            print('Directory not found, listing default directory.')


def establish_connection(server_host, server_port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((server_host, server_port))
        except:
            print('Error binding socket, exiting')
            exit()
        sock.listen()
        print(f'Serving on {server_host} port {server_port} (http://{server_host}:{server_port}/)')
        sock.setblocking(False)
        SEL.register(sock, selectors.EVENT_READ, data=None)

        try:
            while True:
                events = SEL.select(timeout=None)
                for key, mask in events:
                    if key.data is None:
                        accept_client(key.fileobj)
                    else:
                        service_connection(key, mask)
        except KeyboardInterrupt:
            print('\nServer interrupted by keyboard, shuting down...')
        except socket.timeout:
            pass
        finally:
            SEL.close()


if __name__ == '__main__':
    host, port, start_dir = parse_args()

    if start_dir:
        change_directory(start_dir)

    establish_connection(host, port)
