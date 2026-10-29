"""개발용 정적 서버. 캐시를 꺼서 고친 모듈이 바로 반영되게 한다.

python3 -m http.server 는 ES 모듈을 브라우저가 캐시해버려서, 파일을 고쳐도
예전 코드가 계속 돌아간다. 실제로 검증을 옛 코드로 통과시킨 적이 있다.
"""
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, test


class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5604
    directory = sys.argv[2] if len(sys.argv) > 2 else "."
    # 3.14 의 test() 는 directory 를 안 받는다. 핸들러에 묶어서 넘긴다.
    test(HandlerClass=partial(NoCache, directory=directory),
         port=port, bind="127.0.0.1", protocol="HTTP/1.1")
