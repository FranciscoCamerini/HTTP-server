import mimetypes
import os
import pathlib
import time
from html import escape
from urllib import parse
from wsgiref.handlers import format_date_time


SERVER_HEADER = 'Directory Listing Server'
OK_STATUS = '200 OK'


def html_generator(path):
    path = pathlib.Path(path)
    dir_iteration = list(path.iterdir())
    body = f'<html>\n<body>\n<h1>Directory Listing for {escape(path.name)}</h1>\n<ul>\n'.encode()
    yield body
    for file in dir_iteration:
        encoded_name = parse.quote(file.name)
        if file.is_dir():
            encoded_name += '/'
        body = f'<li><a href="{encoded_name}">{escape(file.name)}</a></li>\n'.encode()
        yield body


def get_directory_list(path):
    """
    Create an HTML page generator listing all files inside given directory and it's corresponding headers.
    """
    body_generator = html_generator(path)

    content_length = 0
    for chunk in body_generator:
        content_length += len(chunk)
    body_generator = html_generator(path)

    headers = {
            'Content-Length': content_length,
            'Content-Type': 'text/html; charset=UTF-8',
            'Date': f'{format_date_time(time.time())}',
            'Server': f'{SERVER_HEADER}',
    }

    return body_generator, headers


def read_file_chunk(file, chunk_size):
    with open(file, 'rb') as f:
        while True:
            body = f.read(chunk_size)
            if not body:
                break
            yield body


def get_file_data(filename):
    """
    Create a generator function for body. Set headers based on the content of the file from the request
    """
    body_generator = read_file_chunk(filename, 1024)

    headers = {
        'Content-Length': f'{os.path.getsize(filename)}',
        'Date': f'{format_date_time(time.time())}',
        'Last-Modified': f'{format_date_time(os.path.getmtime(filename))}',
        'Server': f'{SERVER_HEADER}',
    }

    content_type = mimetypes.guess_type(filename)
    if content_type[0]:
        headers['Content-Type'] = content_type[0]
    if content_type[1]:
        headers['Content-Encoding'] = content_type[1]

    return body_generator, headers


def build_http_headers(status, headers):
    headers_str = ''
    for key, value in headers.items():
        headers_str += f'{key}: {value}\r\n'

    response = f'HTTP/1.0 {status}\r\n{headers_str}\r\n'.encode()
    return response


def parse_first_line(request):
    """
    Parse first line from request and return required path and request method.
    """
    headers = request.split('\r\n')
    request_method = headers[0].split()[0]

    path = headers[0].split()[1][1:]
    path = parse.unquote(path)

    return path, request_method


def error_generator(error):
    body = f'<h1>{str(error)}\n<a href="/">Go back to Start Dir</a>'.encode()
    yield body


def handle_exception(error):
    """
    Create a response containing the exception raised, with a link to go back to Start Dir.
    """
    body = error_generator(error)
    content_length = 0
    for chunk in body:
        content_length += len(chunk)
    body = error_generator(error)

    headers = {
            'Content-Length': content_length,
            'Content-Type': 'text/html; charset=UTF-8',
            'Date': f'{format_date_time(time.time())}',
            'Server': f'{SERVER_HEADER}',
    }

    return body, headers


def handle_request(request):
    """
    If path from request = file, opens it.
    If path from request = directory, lists it
    """
    path, request_method = parse_first_line(request)

    start_dir = pathlib.Path.cwd()
    path = pathlib.Path(path).resolve()

    if start_dir not in path.parents:
        path = start_dir

    is_dir = path.is_dir()
    try:
        if not is_dir:
            body, headers = get_file_data(path)
            http_headers = build_http_headers(OK_STATUS, headers)
        else:
            body, headers = get_directory_list(path)
            http_headers = build_http_headers(OK_STATUS, headers)
    except FileNotFoundError as error:
        body, headers = handle_exception(error)
        http_headers = build_http_headers('404 Not Found', headers)

    if request_method == 'HEAD':
        body = None
    elif request_method != 'GET':
        body, headers = handle_exception('Method Not Allowed')
        http_headers = build_http_headers('405 Method Not Allowed', headers)

    return http_headers, body


def receive_client(connection):
    connection.settimeout(2)
    request = b''

    while True:
        request += connection.recv(1024)
        if b'\r\n\r\n' in request:
            break
    request = request.decode()

    headers, body_generator = handle_request(request)
    connection.sendall(headers)

    if body_generator:
        for chunk in body_generator:
            connection.sendall(chunk)

    connection.close()
