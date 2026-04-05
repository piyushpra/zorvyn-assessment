from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from .app import create_app
from .config import Settings, load_settings


class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietRequestHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


def create_server(settings: Settings):
    app = create_app(settings)
    return make_server(
        settings.host,
        settings.port,
        app,
        server_class=ThreadedWSGIServer,
        handler_class=QuietRequestHandler,
    )


def main() -> None:
    settings = load_settings()
    httpd = create_server(settings)
    print(
        "Serving finance backend on http://{host}:{port}".format(
            host=settings.host,
            port=httpd.server_port,
        )
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
