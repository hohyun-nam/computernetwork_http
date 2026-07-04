import argparse
import os
import socket


# 서버는 모든 네트워크 인터페이스에서 8080 포트로 대기한다.
# 0.0.0.0으로 열어두면 UTM 우분투 VM 밖의 맥에서도 접속할 수 있다.
HOST = "0.0.0.0"
PORT = 8080
BUFFER_SIZE = 4096
MAX_UPLOAD_SIZE = 30  # PUT 요청 body가 이 크기를 넘으면 413 응답을 보낸다.

# 서버 파일 위치를 기준으로 www, uploads 폴더 경로를 잡는다.
# 실행 위치가 달라도 server.py가 있는 폴더 기준으로 파일을 찾기 위한 처리이다.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
WWW_DIR = os.path.join(BASE_DIR, "www")
INDEX_FILE = os.path.join(WWW_DIR, "index.html")


def prepare_files():
    # 서버 실행에 필요한 폴더와 protected.txt 파일을 준비한다.
    # protected.txt는 DELETE 403 Forbidden 케이스를 만들기 위한 파일이다.
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(WWW_DIR, exist_ok=True)

    protected_file = os.path.join(UPLOAD_DIR, "protected.txt")
    if not os.path.exists(protected_file):
        with open(protected_file, "w", encoding="utf-8") as file:
            file.write("This file is protected.")


def recv_until_header_end(conn):
    # HTTP 요청에서 Header와 Body는 빈 줄(\r\n\r\n)을 기준으로 나뉜다.
    # 그래서 먼저 Header가 끝나는 지점까지 데이터를 받는다.
    data = b""

    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        data += chunk

    return data


def parse_headers(header_text):
    # 첫 줄(Request Line)에서 method, path, version을 분리한다.
    # 예: GET / HTTP/1.1
    lines = header_text.split("\r\n")
    method, path, version = lines[0].split()

    # 나머지 Header들은 이름으로 쉽게 찾을 수 있도록 딕셔너리로 저장한다.
    # Content-Length 같은 값을 나중에 꺼내기 위해 소문자 key로 저장한다.
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()

    return method, path, version, headers


def recv_body(conn, body_start, content_length):
    # Header 뒤에 body 일부가 이미 같이 들어왔을 수 있으므로 body_start부터 시작한다.
    # 이후 Content-Length에 적힌 크기만큼 부족한 데이터를 계속 수신한다.
    body = body_start

    while len(body) < content_length:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        body += chunk

    return body[:content_length]


def make_response(status_line, body=b"", content_type="text/plain", include_body=True):
    # HTTP Response는 Status Line, Header, 빈 줄, Body 순서로 구성한다.
    # HEAD 요청처럼 body를 보내면 안 되는 경우 include_body=False를 사용한다.
    headers = [
        f"Content-Length: {len(body)}",
        f"Content-Type: {content_type}",
        "Connection: close",
    ]
    response = status_line + "\r\n" + "\r\n".join(headers) + "\r\n\r\n"
    response_bytes = response.encode("utf-8")

    if include_body:
        response_bytes += body

    return response_bytes


def get_static_file_path(path):
    # GET/HEAD 요청의 URL 경로를 server/www 폴더 안의 실제 파일 경로로 바꾼다.
    # / 요청은 웹 서버의 기본 페이지처럼 www/index.html로 처리한다.
    if path == "/":
        return INDEX_FILE

    request_path = path.lstrip("/")
    file_path = os.path.join(WWW_DIR, request_path)

    # 폴더 경로로 요청한 경우에는 그 안의 index.html을 기본 파일로 사용한다.
    # 예: /abc 요청인데 www/abc 폴더가 있으면 www/abc/index.html을 찾는다.
    if os.path.isdir(file_path):
        file_path = os.path.join(file_path, "index.html")

    return file_path


def handle_get(path):
    # GET 요청은 www 폴더에서 해당 파일을 찾아서 보내준다.
    # 파일이 실제로 있으면 200 OK, 없으면 404 Not Found로 응답한다.
    file_path = get_static_file_path(path)
    if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
        with open(file_path, "rb") as file:
            body = file.read()
        return make_response("HTTP/1.1 200 OK", body, "text/html")

    # 파일이 없으면 없는 페이지로 처리한다.
    body = b"Page Not Found"
    return make_response("HTTP/1.1 404 Not Found", body)


def handle_head(path):
    # HEAD는 GET과 같은 방식으로 파일 존재 여부를 확인한다.
    # 단, HTTP 규칙상 응답 body는 보내지 않고 header만 보낸다.
    file_path = get_static_file_path(path)
    if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
        with open(file_path, "rb") as file:
            body = file.read()
        return make_response("HTTP/1.1 200 OK", body, "text/html", include_body=False)

    body = b"Page Not Found"
    return make_response("HTTP/1.1 404 Not Found", body, include_body=False)


def handle_post(path, body):
    # POST는 /message 경로만 처리한다.
    # 다른 경로로 POST가 오면 없는 경로로 보고 404를 반환한다.
    if path != "/message":
        return make_response("HTTP/1.1 404 Not Found", b"Page Not Found")

    # Body가 비어 있으면 보낼 데이터가 없는 요청이므로 400 Bad Request로 처리한다.
    if not body.strip():
        return make_response("HTTP/1.1 400 Bad Request", b"Empty Body")

    # 정상 Body가 오면 메시지가 생성된 것으로 보고 201 Created를 반환한다.
    response_body = b"Message Created: " + body.upper()
    return make_response("HTTP/1.1 201 Created", response_body)


def handle_put(path, body):
    # PUT으로 받은 데이터는 uploads 폴더에 파일로 저장한다.
    # 이 과제에서는 sample.txt와 large.txt 경로만 테스트 대상으로 사용한다.
    filename = os.path.basename(path)

    if path not in ("/sample.txt", "/large.txt"):
        return make_response("HTTP/1.1 404 Not Found", b"Upload Path Not Found")

    # 업로드 크기가 MAX_UPLOAD_SIZE보다 크면 413 Payload Too Large로 처리한다.
    if len(body) > MAX_UPLOAD_SIZE:
        return make_response("HTTP/1.1 413 Payload Too Large", b"File Too Large")

    upload_path = os.path.join(UPLOAD_DIR, filename)
    with open(upload_path, "wb") as file:
        file.write(body)

    return make_response("HTTP/1.1 200 OK", b"Upload Success")


def handle_delete(path):
    # DELETE 요청은 uploads 폴더 안의 파일을 대상으로 처리한다.
    # 파일이 있으면 삭제하고, 없으면 404를 반환한다.
    filename = os.path.basename(path)

    # protected.txt는 삭제 금지 파일로 설정해서 403 Forbidden 케이스를 만든다.
    if filename == "protected.txt":
        return make_response("HTTP/1.1 403 Forbidden", b"Protected File")

    filepath = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(filepath):
        return make_response("HTTP/1.1 404 Not Found", b"File Not Found")

    os.remove(filepath)
    return make_response("HTTP/1.1 200 OK", b"Delete Success")


def handle_client(conn, addr):
    # 클라이언트 하나의 연결에서 HTTP 요청 하나를 처리하는 부분이다.
    # 요청을 읽고, method에 따라 응답을 만든 뒤 연결을 닫는다.
    print(f"\nClient Connected : {addr}")

    try:
        request = recv_until_header_end(conn)
        if not request:
            return

        header_bytes, body_start = request.split(b"\r\n\r\n", 1)
        header_text = header_bytes.decode(errors="replace")
        method, path, version, headers = parse_headers(header_text)
        content_length = int(headers.get("content-length", "0"))
        body = recv_body(conn, body_start, content_length)

        print("\n========== REQUEST HEADER ==========")
        print(header_text)
        if body:
            print("\n========== REQUEST BODY ==========")
            print(body.decode(errors="replace"))

        # Method에 따라 각각의 처리 함수로 분기한다.
        # 여기서 GET/HEAD/POST/PUT/DELETE 케이스별 응답 코드가 결정된다.
        if method == "GET":
            response = handle_get(path)
        elif method == "HEAD":
            response = handle_head(path)
        elif method == "POST":
            response = handle_post(path, body)
        elif method == "PUT":
            response = handle_put(path, body)
        elif method == "DELETE":
            response = handle_delete(path)
        else:
            response = make_response("HTTP/1.1 405 Method Not Allowed", b"Method Not Allowed")

        conn.sendall(response)

        print("\n========== RESPONSE ==========")
        print(response.decode(errors="replace").rstrip())

    except Exception as error:
        response = make_response("HTTP/1.1 400 Bad Request", f"Bad Request: {error}".encode())
        conn.sendall(response)
        print(f"Error: {error}")
    finally:
        conn.close()


def main():
    # --host, --port 옵션을 사용하면 실행할 주소와 포트를 바꿀 수 있다.
    # 기본값은 과제 실행용으로 0.0.0.0:8080을 사용한다.
    parser = argparse.ArgumentParser(description="TCP socket HTTP server")
    parser.add_argument("--host", default=HOST, help="server bind address")
    parser.add_argument("--port", type=int, default=PORT, help="server port")
    args = parser.parse_args()

    prepare_files()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        # 서버를 바로 재실행할 때 포트가 잠겨있는 문제를 줄이기 위한 옵션이다.
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(5)

        print(f"HTTP Server Started ({args.host}:{args.port})")

        try:
            while True:
                conn, addr = server.accept()
                handle_client(conn, addr)
        except KeyboardInterrupt:
            print("\nHTTP Server Stopped")


if __name__ == "__main__":
    main()
