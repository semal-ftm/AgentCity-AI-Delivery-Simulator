"""Start the Agent City dashboard:   python app.py   (then open http://127.0.0.1:8000)"""
import argparse
import threading
import webbrowser

from server import serve


def main() -> None:
    ap = argparse.ArgumentParser(description="Smart Food Delivery - interactive agent simulator")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    httpd = serve(a.port)
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"Agent City is running at {url}   (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
