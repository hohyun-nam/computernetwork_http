## 실행 방법

### 1. 소스 코드 받기

```bash
git clone https://github.com/hohyun-nam/computernetwork_http.git
cd computernetwork_http
```

### 2. Server 실행

UTM Ubuntu VM에서 실행합니다.

```bash
cd server
python3 server.py
```

Server는 기본적으로 `0.0.0.0:8080`에서 실행됩니다.

### 3. Client 실행

macOS에서 실행합니다.

```bash
cd client
python3 client.py --host 192.168.64.2 --port 8080
```

`192.168.64.2`는 Ubuntu VM의 IP 주소입니다. IP가 다르면 `--host` 값을 실제 IP로 바꿔서 실행합니다.


### 4. 전체 테스트 실행

Client 메뉴에서 `a`를 입력하면 전체 HTTP 테스트 케이스가 순서대로 실행됩니다.

## 테스트 케이스

| Case | Request | Response |
| --- | --- | --- |
| 1 | `GET /` | `200 OK` |
| 2 | `GET /abc` | `404 Not Found` |
| 3 | `POST /message` | `201 Created` |
| 4 | `POST /message` empty body | `400 Bad Request` |
| 5 | `PUT /sample.txt` | `200 OK` |
| 6 | `PUT /large.txt` | `413 Payload Too Large` |
| 7 | `DELETE /sample.txt` | `200 OK` |
| 8 | `DELETE /ghost.txt` | `404 Not Found` |
| 9 | `DELETE /protected.txt` | `403 Forbidden` |
| 10 | `HEAD /` | `200 OK` |

