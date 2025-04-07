from multiprocessing import Process
from sbot import main as sbot_main
from gamebot import main as gamebot_main
from chatbot import main as chatbot_main
from utils.constants import *
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

def start_health_check_server():
    """Start a simple HTTP server for Azure health checks."""
    class HealthCheckHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Healthy")
            else:
                self.send_response(404)
                self.end_headers()

    port = int(os.environ.get("PORT", 80))  # Use Azure-provided PORT
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"Health check server running on port {port}")
    server.serve_forever()

def main():
    # Start health check server in a separate thread
    health_check_thread = Process(target=start_health_check_server, daemon=True)

    # create two processes to run sbot and gamebot
    sbot_process = Process(target=sbot_main, args=(TRAVEL_GROUP, GAME_GROUP))
    gamebot_process = Process(target=gamebot_main)
    chatbot_process = Process(target=chatbot_main)

    # start the processes
    sbot_process.start()
    gamebot_process.start()
    chatbot_process.start()
    health_check_thread.start()

    # wait for the processes to finish
    sbot_process.join()
    gamebot_process.join()
    chatbot_process.join()
    health_check_thread.join()

if __name__ == "__main__":
    main()