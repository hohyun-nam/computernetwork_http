import argparse
import socket
import time


# 서버 IP와 포트 번호
# server.py는 UTM 우분투에서 실행하고, client.py는 맥에서 실행하므로
# 우분투에서 ip addr로 확인한 VM IP 주소를 기본 접속 주소로 사용한다.
SERVER_IP = "192.168.64.2"
SERVER_PORT = 8080
BUFFER_SIZE = 4096


def receive_response(client):
    # recv()는 한 번 호출했다고 응답 전체가 무조건 다 오는 것이 아니기 때문에
    # 서버가 Connection: close로 연결을 닫을 때까지 반복해서 응답을 받는다.
    response_chunks = []

    while True:
        chunk = client.recv(BUFFER_SIZE)
        if not chunk:
            break
        response_chunks.append(chunk)

    return b"".join(response_chunks)


def send_request(request_bytes, host, port, title):
    # 하나의 테스트 케이스를 실행하는 함수
    # 먼저 내가 만든 HTTP 요청 메시지를 화면에 출력하고,
    # TCP 소켓으로 서버에 보낸 뒤 서버 응답 메시지도 그대로 출력한다.
    print(f"\n========== {title} ==========")
    print("[Client -> Server]")
    print(request_bytes.decode(errors="replace").rstrip())

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect((host, port))
        # send()는 데이터 일부만 보낼 수도 있어서 요청 전체 전송을 위해 sendall() 사용
        client.sendall(request_bytes)
        response = receive_response(client)

    print("\n[Server -> Client]")
    print(response.decode(errors="replace").rstrip())
    time.sleep(1)


def make_text_request(method, path, host, port, body=""):
    # GET, HEAD, POST, DELETE처럼 문자열 body를 사용하는 요청을 만든다.
    # HTTP 메시지는 Request Line, Header, 빈 줄, Body 순서로 구성되어야 한다.
    request = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "User-Agent: CN-Assignment-Client/1.0\r\n"
        "Connection: close\r\n"
    )

    if method in ("POST", "PUT"):
        body_bytes = body.encode()
        # POST/PUT은 body가 있을 수 있으므로 Content-Length를 넣어
        # 서버가 body를 몇 바이트까지 읽어야 하는지 알 수 있게 한다.
        request += f"Content-Length: {len(body_bytes)}\r\n"
        request += "Content-Type: text/plain\r\n"
    else:
        body_bytes = b""

    request += "\r\n"
    return request.encode() + body_bytes


def make_binary_request(method, path, host, port, body):
    # PUT 요청처럼 파일 데이터나 bytes 데이터를 보내는 경우 사용한다.
    # text가 아니라 bytes 그대로 붙여야 하므로 header만 문자열로 만든 뒤 body와 합친다.
    header = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "User-Agent: CN-Assignment-Client/1.0\r\n"
        "Connection: close\r\n"
        "Content-Type: application/octet-stream\r\n"
        f"Content-Length: {len(body)}\r\n"
        "\r\n"
    ).encode()

    return header + body


def get_cases(host, port):
    # 과제에서 확인할 HTTP Method / Response 테스트 케이스들
    # 각 메뉴 번호마다 요청 메시지를 만들고 send_request()로 전송한다.
    return {
        "1": (
            "GET 200",
            lambda: send_request(
                make_text_request("GET", "/", host, port),
                host,
                port,
                "1. GET / -> 200 OK",
            ),
        ),
        "2": (
            "GET 404",
            lambda: send_request(
                make_text_request("GET", "/abc", host, port),
                host,
                port,
                "2. GET /abc -> 404 Not Found",
            ),
        ),
        "3": (
            "POST 201",
            lambda: send_request(
                make_text_request("POST", "/message", host, port, "hello professor"),
                host,
                port,
                "3. POST /message -> 201 Created",
            ),
        ),
        "4": (
            "POST 400",
            lambda: send_request(
                make_text_request("POST", "/message", host, port, ""),
                host,
                port,
                "4. POST /message empty body -> 400 Bad Request",
            ),
        ),
        "5": (
            "PUT 200",
            lambda: send_request(
                make_binary_request("PUT", "/sample.txt", host, port, b"small file"),
                host,
                port,
                "5. PUT /sample.txt -> 200 OK",
            ),
        ),
        "6": (
            "PUT 413",
            lambda: send_request(
                make_binary_request("PUT", "/large.txt", host, port, b"A" * 100),
                host,
                port,
                "6. PUT /large.txt -> 413 Payload Too Large",
            ),
        ),
        "7": (
            "DELETE 200",
            lambda: send_request(
                make_text_request("DELETE", "/sample.txt", host, port),
                host,
                port,
                "7. DELETE /sample.txt -> 200 OK",
            ),
        ),
        "8": (
            "DELETE 404",
            lambda: send_request(
                make_text_request("DELETE", "/ghost.txt", host, port),
                host,
                port,
                "8. DELETE /ghost.txt -> 404 Not Found",
            ),
        ),
        "9": (
            "DELETE 403",
            lambda: send_request(
                make_text_request("DELETE", "/protected.txt", host, port),
                host,
                port,
                "9. DELETE /protected.txt -> 403 Forbidden",
            ),
        ),
        "10": (
            "HEAD 200",
            lambda: send_request(
                make_text_request("HEAD", "/", host, port),
                host,
                port,
                "10. HEAD / -> 200 OK",
            ),
        ),
    }


def print_menu(cases):
    # 사용자가 원하는 테스트 케이스를 하나씩 선택하거나
    # 전체 케이스를 한 번에 실행할 수 있도록 메뉴를 출력한다.
    print("\n========== MENU ==========")
    for key, (title, _) in cases.items():
        print(f"{key}. {title}")
    print("a. RUN ALL")
    print("0. EXIT")


def main():
    # 실행할 때 --host, --port 옵션으로 서버 주소를 바꿀 수 있게 했다.
    # VM IP가 달라져도 코드 수정 없이 명령어 옵션만 바꾸면 된다.
    parser = argparse.ArgumentParser(description="TCP socket HTTP client")
    parser.add_argument("--host", default=SERVER_IP, help="server IP address")
    parser.add_argument("--port", type=int, default=SERVER_PORT, help="server port")
    args = parser.parse_args()

    cases = get_cases(args.host, args.port)

    while True:
        print_menu(cases)
        menu = input("Select : ").strip().lower()

        if menu == "0":
            break
        if menu == "a":
            # a를 입력하면 영상 촬영 시 편하도록 전체 케이스를 순서대로 실행한다.
            for _, run_case in cases.values():
                run_case()
            continue
        if menu in cases:
            cases[menu][1]()
        else:
            print("Wrong Menu")


if __name__ == "__main__":
    main()
