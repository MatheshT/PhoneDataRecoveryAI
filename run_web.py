import sys
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import uvicorn

def main():
    print("================================================================================")
    print("      LAUNCHING PHONE FORENSIC RECOVERY & AI WEB APPLICATION")
    print("================================================================================")
    print("[*] Starting local server at: http://127.0.0.1:8000")
    print("[*] Default Timeframe: Last 1 Month")
    print("[*] Opening dashboard in your default browser...")
    print("================================================================================\n")

    # Automatically open browser after 1 second
    try:
        import threading
        def open_browser():
            time.sleep(1.2)
            webbrowser.open("http://127.0.0.1:8000")
        threading.Thread(target=open_browser, daemon=True).start()
    except Exception:
        pass

    uvicorn.run("web_app.server:app", host="127.0.0.1", port=8000, log_level="info")

if __name__ == "__main__":
    main()
