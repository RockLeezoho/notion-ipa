import os
import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import requests
import time
import sys
import socket
import shutil


# =========================================================
# CONFIG
# =========================================================

HOST = "127.0.0.1"
PORT = 8000

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_LOG_FILE = os.path.join(BASE_DIR, "notion_ipa.log")

NGROK_DOMAIN = os.getenv("NGROK_DOMAIN")
NGROK_REGION = os.getenv("NGROK_REGION")

# Resolve the exact ngrok executable visible to this Python process.
# This avoids PATH differences between CMD, Git Bash, and the GUI process.
NGROK_EXE = shutil.which("ngrok")

UVICORN_COMMAND = [
    sys.executable,
    "-m",
    "uvicorn",
    "app:app",
    "--host",
    HOST,
    "--port",
    str(PORT),
]


def build_ngrok_command():
    """Build the ngrok command using the executable visible to Python."""

    if not NGROK_EXE:
        raise FileNotFoundError(
            "ngrok.exe was not found in this Python process PATH. "
            "Run `where ngrok` and verify the GUI is started from the "
            "same environment."
        )

    command = [NGROK_EXE, "http"]

    if NGROK_REGION:
        command.extend(["--region", NGROK_REGION])

    if NGROK_DOMAIN:
        command.extend(["--domain", NGROK_DOMAIN])

    command.append(str(PORT))
    return command


NGROK_API = "http://127.0.0.1:4040/api/tunnels"

CREATE_NO_WINDOW = getattr(
    subprocess,
    "CREATE_NO_WINDOW",
    0
)


# =========================================================
# COLORS
# =========================================================

BG = "#F5F7FB"
CARD = "#FFFFFF"

TEXT = "#1F2937"
MUTED = "#6B7280"

BLUE = "#2563EB"
BLUE_DARK = "#1D4ED8"

GREEN = "#16A34A"
GREEN_BG = "#DCFCE7"

RED = "#DC2626"
RED_BG = "#FEE2E2"

ORANGE = "#EA580C"
ORANGE_BG = "#FFEDD5"

GRAY = "#E5E7EB"
GRAY_DARK = "#374151"

LOG_BG = "#111827"
LOG_TEXT = "#D1D5DB"


# =========================================================
# MAIN APP
# =========================================================

class DesktopApp:

    def __init__(self, root):
        self.root = root

        self.root.title("Notion IPA Automation")
        self.root.geometry("620x560")
        self.root.minsize(520, 500)
        self.root.configure(bg=BG)

        self.fastapi_process = None
        self.ngrok_process = None

        self.fastapi_started_by_app = False
        self.ngrok_started_by_app = False

        self.webhook_url = ""

        self.create_ui()

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.on_close
        )

        self.refresh_status()


    # =====================================================
    # UI
    # =====================================================

    def create_ui(self):

        # -------------------------------------------------
        # Header
        # -------------------------------------------------

        header = tk.Frame(
            self.root,
            bg=BG
        )
        header.pack(
            fill="x",
            padx=24,
            pady=(20, 10)
        )

        title = tk.Label(
            header,
            text="Notion IPA",
            font=("Segoe UI", 22, "bold"),
            bg=BG,
            fg=TEXT
        )
        title.pack(anchor="w")

        subtitle = tk.Label(
            header,
            text="Notion → Oxford → IPA",
            font=("Segoe UI", 10),
            bg=BG,
            fg=MUTED
        )
        subtitle.pack(anchor="w", pady=(2, 0))


        # -------------------------------------------------
        # Status Cards
        # -------------------------------------------------

        status_frame = tk.Frame(
            self.root,
            bg=BG
        )
        status_frame.pack(
            fill="x",
            padx=24,
            pady=(5, 10)
        )

        self.fastapi_status = self.create_status_card(
            status_frame,
            "FastAPI",
            "Stopped",
            RED,
            0
        )

        self.ngrok_status = self.create_status_card(
            status_frame,
            "ngrok",
            "Stopped",
            RED,
            1
        )

        self.webhook_status = self.create_status_card(
            status_frame,
            "Webhook",
            "Inactive",
            RED,
            2
        )


        # -------------------------------------------------
        # Local Server Card
        # -------------------------------------------------

        server_card = tk.Frame(
            self.root,
            bg=CARD,
            highlightbackground=GRAY,
            highlightthickness=1
        )
        server_card.pack(
            fill="x",
            padx=24,
            pady=6
        )

        tk.Label(
            server_card,
            text="Local Server",
            font=("Segoe UI", 10, "bold"),
            bg=CARD,
            fg=TEXT
        ).pack(
            anchor="w",
            padx=16,
            pady=(12, 2)
        )

        self.server_info = tk.Label(
            server_card,
            text=f"http://{HOST}:{PORT}",
            font=("Consolas", 10),
            bg=CARD,
            fg=MUTED
        )
        self.server_info.pack(
            anchor="w",
            padx=16,
            pady=(0, 12)
        )


        # -------------------------------------------------
        # Webhook URL Card
        # -------------------------------------------------

        webhook_card = tk.Frame(
            self.root,
            bg=CARD,
            highlightbackground=GRAY,
            highlightthickness=1
        )
        webhook_card.pack(
            fill="x",
            padx=24,
            pady=6
        )

        tk.Label(
            webhook_card,
            text="Public Webhook URL",
            font=("Segoe UI", 10, "bold"),
            bg=CARD,
            fg=TEXT
        ).pack(
            anchor="w",
            padx=16,
            pady=(12, 4)
        )

        url_frame = tk.Frame(
            webhook_card,
            bg=CARD
        )
        url_frame.pack(
            fill="x",
            padx=16,
            pady=(0, 12)
        )

        self.url_entry = tk.Entry(
            url_frame,
            font=("Consolas", 9),
            relief="flat",
            bg="#F9FAFB",
            fg=TEXT
        )
        self.url_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=7
        )

        self.copy_button = tk.Button(
            url_frame,
            text="COPY",
            command=self.copy_webhook_url,
            font=("Segoe UI", 9, "bold"),
            bg=BLUE,
            fg="white",
            activebackground=BLUE_DARK,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=16,
            pady=6,
            cursor="hand2"
        )
        self.copy_button.pack(
            side="left",
            padx=(8, 0)
        )


        # -------------------------------------------------
        # Control Buttons
        # -------------------------------------------------

        button_frame = tk.Frame(
            self.root,
            bg=BG
        )
        button_frame.pack(
            fill="x",
            padx=24,
            pady=(10, 8)
        )

        self.start_button = tk.Button(
            button_frame,
            text="START",
            command=self.start_system,
            font=("Segoe UI", 10, "bold"),
            bg=GREEN,
            fg="white",
            activebackground="#15803D",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=22,
            pady=9,
            cursor="hand2"
        )
        self.start_button.pack(
            side="left"
        )

        self.stop_button = tk.Button(
            button_frame,
            text="STOP",
            command=self.stop_system,
            font=("Segoe UI", 10, "bold"),
            bg=RED,
            fg="white",
            activebackground="#B91C1C",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=22,
            pady=9,
            cursor="hand2"
        )
        self.stop_button.pack(
            side="left",
            padx=(8, 0)
        )


        # -------------------------------------------------
        # Activity Log
        # -------------------------------------------------

        log_header = tk.Frame(
            self.root,
            bg=BG
        )
        log_header.pack(
            fill="x",
            padx=24,
            pady=(6, 3)
        )

        tk.Label(
            log_header,
            text="Activity Log",
            font=("Segoe UI", 10, "bold"),
            bg=BG,
            fg=TEXT
        ).pack(
            side="left"
        )

        clear_button = tk.Button(
            log_header,
            text="Clear",
            command=self.clear_log,
            font=("Segoe UI", 8),
            bg=BG,
            fg=MUTED,
            activebackground=BG,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            cursor="hand2"
        )
        clear_button.pack(
            side="right"
        )

        log_frame = tk.Frame(
            self.root,
            bg=LOG_BG
        )
        log_frame.pack(
            fill="both",
            expand=True,
            padx=24,
            pady=(0, 20)
        )

        self.log_text = tk.Text(
            log_frame,
            bg=LOG_BG,
            fg=LOG_TEXT,
            insertbackground="white",
            font=("Consolas", 9),
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            wrap="word"
        )
        self.log_text.pack(
            fill="both",
            expand=True
        )


    # =====================================================
    # STATUS CARD
    # =====================================================

    def create_status_card(
        self,
        parent,
        title,
        status,
        color,
        column
    ):

        card = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=GRAY,
            highlightthickness=1
        )

        card.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=4
        )

        parent.grid_columnconfigure(
            column,
            weight=1
        )

        indicator = tk.Label(
            card,
            text="●",
            font=("Segoe UI", 14),
            bg=CARD,
            fg=color
        )
        indicator.pack(
            pady=(10, 0)
        )

        title_label = tk.Label(
            card,
            text=title,
            font=("Segoe UI", 9, "bold"),
            bg=CARD,
            fg=TEXT
        )
        title_label.pack(
            pady=(2, 0)
        )

        status_label = tk.Label(
            card,
            text=status,
            font=("Segoe UI", 8),
            bg=CARD,
            fg=MUTED
        )
        status_label.pack(
            pady=(0, 10)
        )

        return {
            "card": card,
            "indicator": indicator,
            "title": title_label,
            "status": status_label
        }


    def update_status_card(
        self,
        card,
        status,
        color
    ):

        card["indicator"].configure(
            fg=color
        )

        card["status"].configure(
            text=status
        )


    # =====================================================
    # LOG
    # =====================================================

    def log(self, message):

        timestamp = time.strftime("%H:%M:%S")

        self.log_text.insert(
            "end",
            f"[{timestamp}] {message}\n"
        )

        self.log_text.see("end")


    def clear_log(self):

        self.log_text.delete(
            "1.0",
            "end"
        )


    # =====================================================
    # PORT CHECK
    # =====================================================

    def is_port_open(self):

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(0.5)

        try:
            result = sock.connect_ex(
                (HOST, PORT)
            )

            return result == 0

        except Exception:
            return False

        finally:
            sock.close()


    def get_port_pid(self):

        try:

            result = subprocess.run(
                [
                    "netstat",
                    "-ano"
                ],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW
            )

            for line in result.stdout.splitlines():

                if (
                    f"{HOST}:{PORT}" in line
                    and "LISTENING" in line
                ):

                    parts = line.split()

                    if parts:
                        return parts[-1]

        except Exception:
            pass

        return None


    def get_process_name(self, pid):

        if not pid:
            return None

        try:

            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    f"PID eq {pid}"
                ],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW
            )

            lines = result.stdout.splitlines()

            for line in lines:

                if pid in line:

                    return line.split()[0]

        except Exception:
            pass

        return None


    # =====================================================
    # EXISTING FASTAPI CHECK
    # =====================================================

    def check_existing_fastapi(self):

        if not self.is_port_open():
            return False

        try:

            response = requests.get(
                f"http://{HOST}:{PORT}/",
                timeout=1
            )

            if response.status_code < 500:

                self.log(
                    "Existing server detected on port 8000."
                )

                return True

        except Exception:
            pass

        pid = self.get_port_pid()

        process_name = self.get_process_name(
            pid
        )

        if pid:

            self.log(
                f"Port 8000 is occupied by PID {pid}"
            )

            if process_name:

                self.log(
                    f"Process: {process_name}"
                )

        return False


    # =====================================================
    # START SYSTEM
    # =====================================================

    def start_system(self):

        self.start_button.configure(
            state="disabled"
        )

        threading.Thread(
            target=self.start_system_worker,
            daemon=True
        ).start()


    def start_system_worker(self):

        self.log(
            "Starting automation system..."
        )

        # -------------------------------------------------
        # Check existing FastAPI
        # -------------------------------------------------

        if self.check_existing_fastapi():

            self.fastapi_started_by_app = False

            self.update_status_card(
                self.fastapi_status,
                "Running",
                GREEN
            )

            self.log(
                "Using the existing FastAPI server."
            )

        else:

            # ---------------------------------------------
            # Port occupied
            # ---------------------------------------------

            if self.is_port_open():

                pid = self.get_port_pid()

                process_name = self.get_process_name(
                    pid
                )

                message = (
                    "Port 8000 is already occupied."
                )

                if pid:
                    message += f" PID: {pid}."

                if process_name:
                    message += (
                        f" Process: {process_name}."
                    )

                self.log(
                    message
                )

                self.start_button.configure(
                    state="normal"
                )

                return

            # ---------------------------------------------
            # Start FastAPI
            # ---------------------------------------------

            self.log(
                "Starting FastAPI server..."
            )

            try:

                self.fastapi_process = subprocess.Popen(
                    UVICORN_COMMAND,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW
                )

                self.fastapi_started_by_app = True

                threading.Thread(
                    target=self.read_process_output,
                    args=(
                        self.fastapi_process,
                        "FastAPI"
                    ),
                    daemon=True
                ).start()

            except Exception as e:

                self.log(
                    f"Failed to start FastAPI: {e}"
                )

                self.start_button.configure(
                    state="normal"
                )

                return


            # ---------------------------------------------
            # Wait for FastAPI
            # ---------------------------------------------

            ready = False

            for _ in range(30):

                time.sleep(0.5)

                if self.is_port_open():

                    ready = True
                    break

            if not ready:

                self.log(
                    "FastAPI did not start successfully."
                )

                self.start_button.configure(
                    state="normal"
                )

                return

            self.log(
                "FastAPI server is running."
            )

            self.update_status_card(
                self.fastapi_status,
                "Running",
                GREEN
            )


        # =================================================
        # START NGROK
        # =================================================

        self.log(
            "Starting ngrok tunnel..."
        )

        public_url = self.get_ngrok_url()

        if public_url:
            self.log(
                f"Using existing ngrok tunnel: {public_url}"
            )

        else:
            try:

                ngrok_command = build_ngrok_command()

                self.log(
                    f"ngrok executable: {NGROK_EXE}"
                )
                self.log(
                    f"Starting ngrok with command: {' '.join(ngrok_command)}"
                )

                self.ngrok_process = subprocess.Popen(
                    ngrok_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW
                )

                self.ngrok_started_by_app = True

                threading.Thread(
                    target=self.read_process_output,
                    args=(
                        self.ngrok_process,
                        "ngrok"
                    ),
                    daemon=True
                ).start()

            except Exception as e:

                self.log(
                    f"Failed to start ngrok: {e}"
                )

                self.start_button.configure(
                    state="normal"
                )

                return


        # -------------------------------------------------
        # Wait for ngrok URL
        # -------------------------------------------------

        if not public_url:
            for _ in range(30):

                time.sleep(0.5)

                if (
                    self.ngrok_process
                    and self.ngrok_process.poll() is not None
                ):
                    self.log(
                        f"ngrok exited with code "
                        f"{self.ngrok_process.returncode}."
                    )
                    break

                public_url = self.get_ngrok_url()

                if public_url:
                    break

        if public_url:

            self.webhook_url = (
                f"{public_url}/webhook/notion"
            )

            self.url_entry.delete(
                0,
                "end"
            )

            self.url_entry.insert(
                0,
                self.webhook_url
            )

            self.update_status_card(
                self.ngrok_status,
                "Running",
                GREEN
            )

            self.update_status_card(
                self.webhook_status,
                "Active",
                GREEN
            )

            self.log(
                f"ngrok tunnel: {public_url}"
            )

            self.log(
                f"Webhook URL: {self.webhook_url}"
            )

            self.log(
                "Automation system is ready."
            )

        else:

            self.log(
                "Could not detect the ngrok public URL."
            )

            self.update_status_card(
                self.ngrok_status,
                "Error",
                RED
            )

        self.start_button.configure(
            state="normal"
        )


    # =====================================================
    # PROCESS OUTPUT
    # =====================================================

    def read_process_output(
        self,
        process,
        name
    ):

        try:

            for line in iter(
                process.stdout.readline,
                ""
            ):

                line = line.strip()

                if line:

                    self.log(
                        f"[{name}] {line}"
                    )

        except Exception as e:

            self.log(
                f"[{name}] Output error: {e}"
            )


    # =====================================================
    # NGROK URL
    # =====================================================

    def get_ngrok_url(self):

        try:
            response = requests.get(
                NGROK_API,
                timeout=1
            )
            response.raise_for_status()

            data = response.json()
            tunnels = data.get("tunnels", [])

            preferred = None

            for tunnel in tunnels:
                public_url = tunnel.get("public_url")

                if not public_url or not public_url.startswith("https://"):
                    continue

                public_url = public_url.rstrip("/")

                if NGROK_DOMAIN:
                    configured_domain = NGROK_DOMAIN.replace(
                        "https://",
                        ""
                    ).rstrip("/")

                    if public_url.endswith(configured_domain):
                        return public_url

                if preferred is None:
                    preferred = public_url

            return preferred

        except (requests.RequestException, ValueError, OSError):
            return None


    # =====================================================
    # WEBHOOK TEST
    # =====================================================

    def test_local_webhook(self):
        """Test the FastAPI webhook without involving Notion/ngrok."""

        try:
            response = requests.post(
                f"http://{HOST}:{PORT}/webhook/notion",
                json={
                    "test": True,
                    "source": "desktop_app"
                },
                timeout=5
            )

            self.log(
                f"Local webhook test: HTTP {response.status_code}"
            )

            if response.text:
                self.log(
                    f"Local webhook response: {response.text[:300]}"
                )

        except requests.RequestException as e:
            self.log(
                f"Local webhook test failed: {e}"
            )


    # =====================================================
    # COPY WEBHOOK URL
    # =====================================================

    def copy_webhook_url(self):

        url = self.url_entry.get().strip()

        if not url:
            return

        self.root.clipboard_clear()
        self.root.clipboard_append(url)

        self.log(
            "Webhook URL copied to clipboard."
        )


    # =====================================================
    # STOP SYSTEM
    # =====================================================

    def stop_system(self):

        self.log(
            "Stopping automation system..."
        )

        # -------------------------------------------------
        # Stop ngrok
        # -------------------------------------------------

        if (
            self.ngrok_process
            and self.ngrok_started_by_app
        ):

            try:
                self.ngrok_process.terminate()
            except Exception:
                pass

            self.ngrok_process = None

            self.ngrok_started_by_app = False

        # -------------------------------------------------
        # Stop FastAPI
        # -------------------------------------------------

        if (
            self.fastapi_process
            and self.fastapi_started_by_app
        ):

            try:
                self.fastapi_process.terminate()
            except Exception:
                pass

            self.fastapi_process = None

            self.fastapi_started_by_app = False

        self.update_status_card(
            self.fastapi_status,
            "Stopped",
            RED
        )

        self.update_status_card(
            self.ngrok_status,
            "Stopped",
            RED
        )

        self.update_status_card(
            self.webhook_status,
            "Inactive",
            RED
        )

        self.url_entry.delete(
            0,
            "end"
        )

        self.webhook_url = ""

        self.log(
            "Automation system stopped."
        )


    # =====================================================
    # REFRESH STATUS
    # =====================================================

    def refresh_status(self):

        try:

            # ---------------------------------------------
            # FastAPI
            # ---------------------------------------------

            if self.is_port_open():

                self.update_status_card(
                    self.fastapi_status,
                    "Running",
                    GREEN
                )

            else:

                self.update_status_card(
                    self.fastapi_status,
                    "Stopped",
                    RED
                )


            # ---------------------------------------------
            # ngrok
            # ---------------------------------------------

            public_url = self.get_ngrok_url()

            if public_url:

                self.update_status_card(
                    self.ngrok_status,
                    "Running",
                    GREEN
                )

                self.update_status_card(
                    self.webhook_status,
                    "Active",
                    GREEN
                )

            else:

                self.update_status_card(
                    self.ngrok_status,
                    "Stopped",
                    RED
                )

                self.update_status_card(
                    self.webhook_status,
                    "Inactive",
                    RED
                )

                if self.webhook_url:
                    self.url_entry.delete(0, "end")
                    self.webhook_url = ""

        except Exception:
            pass

        self.root.after(
            1000,
            self.refresh_status
        )


    # =====================================================
    # CLOSE APP
    # =====================================================

    def on_close(self):

        answer = messagebox.askyesno(
            "Exit",
            "Do you want to exit the application?"
        )

        if not answer:
            return

        self.stop_system()

        self.root.destroy()


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = DesktopApp(root)

    root.mainloop()
