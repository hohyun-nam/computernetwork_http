import argparse
import os
import socket


# 서버는 모든 네트워크 인터페이스에서 8080 포트로 대기
HOST = "0.0.0.0"
PORT = 8080
BUFFER_SIZE = 4096
MAX_UPLOAD_SIZE = 30  # 이 크기를 넘으면 413 응답을 보내기 위한 기준

# 서버 파일 위치를 기준으로 www, uploads 폴더 경로 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
WWW_DIR = os.path.join(BASE_DIR, "www")
INDEX_FILE = os.path.join(WWW_DIR, "index.html")


def prepare_files():
    # 서버 실행에 필요한 폴더와 기본 파일 준비
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(WWW_DIR, exist_ok=True)

    protected_file = os.path.join(UPLOAD_DIR, "protected.txt")
    if not os.path.exists(protected_file):
        with open(protected_file, "w", encoding="utf-8") as file:
            file.write("This file is protected.")


def recv_until_header_end(conn):
    # HTTP Header는 \r\n\r\n에서 끝나므로 그 지점까지 먼저 수신
    data = b""

    while b"\r\n\r\n" not in data:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        data += chunk

    return data


def parse_headers(header_text):
    # Request Line에서 method, path, version을 분리
    lines = header_text.split("\r\n")
    method, path, version = lines[0].split()

    # 나머지 Header들은 딕셔너리로 저장
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()

    return method, path, version, headers


def recv_body(conn, body_start, content_length):
    # Content-Length에 적힌 크기만큼 Body를 끝까지 수신
    body = body_start

    while len(body) < content_length:
        chunk = conn.recv(BUFFER_SIZE)
        if not chunk:
            break
        body += chunk

    return body[:content_length]


def make_response(status_line, body=b"", content_type="text/plain", include_body=True):
    # HTTP Response는 Status Line + Header + 빈 줄 + Body 순서로 구성
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
    # URL 경로를 server/www 폴더 안의 실제 파일 경로로 바꿔줌
    # / 요청은 기본 페이지인 www/index.html로 처리
    if path == "/":
        return INDEX_FILE

    request_path = path.lstrip("/")
    file_path = os.path.join(WWW_DIR, request_path)

    # 폴더 경로로 요청한 경우에는 그 안의 index.html을 기본 파일로 사용
    if os.path.isdir(file_path):
        file_path = os.path.join(file_path, "index.html")

    return file_path


def handle_get(path):
    # GET 요청 경로에 해당하는 파일이 www 폴더 안에 있으면 200 OK 반환
    file_path = get_static_file_path(path)
    if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
        with open(file_path, "rb") as file:
            body = file.read()
        return make_response("HTTP/1.1 200 OK", body, "text/html")

    # 파일이 없으면 없는 페이지로 처리
    body = b"Page Not Found"
    return make_response("HTTP/1.1 404 Not Found", body)


def handle_head(path):
    # HEAD는 GET과 비슷하지만 Body는 보내지 않음
    file_path = get_static_file_path(path)
    if file_path and os.path.exists(file_path) and os.path.isfile(file_path):
        with open(file_path, "rb") as file:
            body = file.read()
        return make_response("HTTP/1.1 200 OK", body, "text/html", include_body=False)

    body = b"Page Not Found"
    return make_response("HTTP/1.1 404 Not Found", body, include_body=False)


def handle_post(path, body):
    # POST는 /message 경로만 처리
    if path != "/message":
        return make_response("HTTP/1.1 404 Not Found", b"Page Not Found")

    # Body가 비어 있으면 잘못된 요청으로 판단
    if not body.strip():
        return make_response("HTTP/1.1 400 Bad Request", b"Empty Body")

    # 정상 Body가 오면 생성 성공으로 201 응답
    response_body = b"Message Created: " + body.upper()
    return make_response("HTTP/1.1 201 Created", response_body)


def handle_put(path, body):
    # PUT으로 받은 데이터는 uploads 폴더에 파일로 저장
    filename = os.path.basename(path)

    if path not in ("/sample.txt", "/large.txt"):
        return make_response("HTTP/1.1 404 Not Found", b"Upload Path Not Found")

    # 크기가 너무 크면 413 응답
    if len(body) > MAX_UPLOAD_SIZE:
        return make_response("HTTP/1.1 413 Payload Too Large", b"File Too Large")

    upload_path = os.path.join(UPLOAD_DIR, filename)
    with open(upload_path, "wb") as file:
        file.write(body)

    return make_response("HTTP/1.1 200 OK", b"Upload Success")


def handle_delete(path):
    # DELETE 요청은 uploads 폴더 안의 파일을 대상으로 처리
    filename = os.path.basename(path)

    # protected.txt는 삭제 금지 파일로 설정
    if filename == "protected.txt":
        return make_response("HTTP/1.1 403 Forbidden", b"Protected File")

    filepath = os.path.join(UPLOAD_DIR, filename)

    if not os.path.exists(filepath):
        return make_response("HTTP/1.1 404 Not Found", b"File Not Found")

    os.remove(filepath)
    return make_response("HTTP/1.1 200 OK", b"Delete Success")


def handle_client(conn, addr):
    # 클라이언트 하나의 요청을 처리하는 부분
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

        # Method에 따라 각각의 처리 함수로 분기
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
    # --host, --port 옵션을 사용하면 실행할 주소와 포트를 바꿀 수 있음
    parser = argparse.ArgumentParser(description="TCP socket HTTP server")
    parser.add_argument("--host", default=HOST, help="server bind address")
    parser.add_argument("--port", type=int, default=PORT, help="server port")
    args = parser.parse_args()

    prepare_files()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        # 서버를 바로 재실행할 때 포트가 잠겨있는 문제를 줄이기 위한 옵션
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
