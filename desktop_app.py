import sys
import threading
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QTimer
import uvicorn
import requests
import time

def run_fastapi():
    from app.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BCR Analysis Tool")
        self.setGeometry(100, 100, 1200, 800)
        self.web_view = QWebEngineView()
        self.setCentralWidget(self.web_view)
        self.check_server_and_load()

    def check_server_and_load(self):
        def is_server_up():
            try:
                requests.get("http://127.0.0.1:8000", timeout=0.5)
                return True
            except Exception:
                return False

        # Try for up to 5 seconds
        for _ in range(20):
            if is_server_up():
                self.web_view.setUrl(QUrl("http://127.0.0.1:8000"))
                return
            time.sleep(0.25)
        # If not up after 5 seconds, show error page
        self.web_view.setHtml("<h1>Could not connect to backend server.</h1>")

if __name__ == "__main__":
    # Start FastAPI in a background thread
    api_thread = threading.Thread(target=run_fastapi, daemon=True)
    api_thread.start()

    # Start the Qt application
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
