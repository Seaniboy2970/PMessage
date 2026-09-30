import tkinter as tk
from tkinter import messagebox, simpledialog
import requests
import threading
import time
import base64
import hashlib
from cryptography.fernet import Fernet, InvalidToken

SERVER_URL = "http://127.0.0.1:5000"  # Ersetze 127.0.0.1 durch die IP deines Raspberry Pi

class SecureChatClient:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Secure Messenger")
        self.root.geometry("520x550")
        
        self.username = ""
        self.secret_key = ""
        self.current_room = "Lobby"
        self.running = False
        self.last_room_msg_count = 0

        # Login + Passwort-Abfrage
        if not self.login_dialog():
            self.root.destroy()
            return

        self.setup_ui()
        
        # Hintergrund-Polling starten
        self.running = True
        self.poll_thread = threading.Thread(target=self.fetch_loop, daemon=True)
        self.poll_thread.start()

    # --- KRYPTO-LOGIK (Rolling Keys) ---

    def _get_fernet_instance(self, offset_blocks=0):
        """
        Generiert einen AES-256 Key basierend auf:
        [Start-Passwort] + [2-Minuten-Zeitblock (time // 120)]
        """
        time_block = int(time.time() // 120) + offset_blocks
        combined = f"{self.secret_key}:{time_block}".encode('utf-8')
        
        # Hash erzeugen (32 Bytes) und für Fernet Base64-kodieren
        key_32bytes = hashlib.sha256(combined).digest()
        fernet_key = base64.urlsafe_b64encode(key_32bytes)
        return Fernet(fernet_key)

    def encrypt(self, plain_text: str) -> str:
        """Verschlüsselt mit dem aktuell gültigen 2-Minuten-Schlüssel."""
        f = self._get_fernet_instance(offset_blocks=0)
        return f.encrypt(plain_text.encode('utf-8')).decode('utf-8')

    def decrypt(self, cipher_text: str) -> str:
        """
        Entschlüsselt die Nachricht. Probiert erst den aktuellen 2-Minuten-Block
        und bei Fehlschlag den vorherigen Block (-120 Sek), um Latenzen abzufangen.
        """
        for offset in [0, -1]:
            try:
                f = self._get_fernet_instance(offset_blocks=offset)
                return f.decrypt(cipher_text.encode('utf-8')).decode('utf-8')
            except (InvalidToken, Exception):
                continue
        return "🔒 [Entschlüsselung fehlgeschlagen - Falsches Passwort oder abgelaufen]"

    # --- DIALOGE & GUI ---

    def login_dialog(self):
        # 1. Username abfragen
        while True:
            name = simpledialog.askstring("Login", "Wähle deinen Usernamen:", parent=self.root)
            if not name:
                return False
            name = name.strip()
            try:
                res = requests.post(f"{SERVER_URL}/login", json={"username": name})
                if res.status_code == 200:
                    self.username = name
                    break
                elif res.status_code == 409:
                    messagebox.showerror("Fehler", "Dieser Username ist bereits vergeben!")
                else:
                    messagebox.showerror("Fehler", f"Serverfehler: {res.json().get('message')}")
            except Exception as e:
                messagebox.showerror("Verbindungsfehler", f"Server nicht erreichbar: {e}")
                return False

        # 2. Gemeinsames Verschlüsselungswort abfragen
        secret = simpledialog.askstring("Verschlüsselung", "Gib das gemeinsame Start-Passwort ein:", parent=self.root, show="*")
        if not secret:
            return False
        
        self.secret_key = secret.strip()
        messagebox.showinfo("Erfolg", f"Willkommen, {self.username}!\nEnde-zu-Ende-Verschlüsselung mit 2-Minuten-Rotation ist aktiv.")
        return True

    def setup_ui(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)

        self.lbl_info = tk.Label(
            top_frame, 
            text=f"User: {self.username} | Raum: {self.current_room}", 
            font=("Arial", 10, "bold")
        )
        self.lbl_info.pack(side=tk.LEFT)

        btn_invite = tk.Button(top_frame, text="User einladen", command=self.invite_user)
        btn_invite.pack(side=tk.RIGHT)

        self.chat_display = tk.Text(self.root, state=tk.DISABLED, wrap=tk.WORD)
        self.chat_display.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        input_frame = tk.Frame(self.root)
        input_frame.pack(fill=tk.X, padx=10, pady=10)

        self.msg_entry = tk.Entry(input_frame)
        self.msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.msg_entry.bind("<Return>", lambda e: self.send_message())

        btn_send = tk.Button(input_frame, text="Senden", command=self.send_message)
        btn_send.pack(side=tk.RIGHT)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- NETZWERK & NACHRICHTEN ---

    def send_message(self):
        text = self.msg_entry.get().strip()
        if not text:
            return
        
        # 1. Nachricht lokal verschlüsseln
        encrypted_payload = self.encrypt(text)
        
        # 2. Paket bauen: ABSENDER|ZIEL|TAG|GEHEIMTEXT
        packet = f"{self.username}|{self.current_room}|-|{encrypted_payload}"
        
        try:
            res = requests.post(f"{SERVER_URL}/send_room", json={"room": self.current_room, "message": packet})
            if res.status_code == 200:
                self.msg_entry.delete(0, tk.END)
        except Exception as e:
            self.append_text(f"[SYSTEM] Sende-Fehler: {e}\n")

    def invite_user(self):
        target = simpledialog.askstring("Einladen", "Welchen User möchtest du einladen?")
        if target:
            target = target.strip()
            # Der Raumname selbst wird ebenfalls verschlüsselt übertragen
            encrypted_room = self.encrypt(self.current_room)
            packet = f"{self.username}|{target}|I|{encrypted_room}"
            try:
                res = requests.post(f"{SERVER_URL}/send_direct", json={"target": target, "message": packet})
                if res.status_code == 200:
                    self.append_text(f"[SYSTEM] Verschlüsselte Einladung an '{target}' gesendet.\n")
                else:
                    messagebox.showerror("Fehler", f"User '{target}' existiert nicht oder ist offline.")
            except Exception as e:
                messagebox.showerror("Fehler", f"Einladung konnte nicht gesendet werden: {e}")

    def fetch_loop(self):
        while self.running:
            try:
                # 1. Raumnachrichten abholen
                res_room = requests.get(f"{SERVER_URL}/get_room/{self.current_room}")
                if res_room.status_code == 200:
                    msgs = res_room.json().get("messages", [])
                    if len(msgs) > self.last_room_msg_count:
                        new_msgs = msgs[self.last_room_msg_count:]
                        self.last_room_msg_count = len(msgs)
                        for raw_msg in new_msgs:
                            self.root.after(0, self.process_incoming, raw_msg)

                # 2. Persönliches Postfach abfragen (Einladungen)
                res_direct = requests.get(f"{SERVER_URL}/get_direct/{self.username}")
                if res_direct.status_code == 200:
                    direct_msgs = res_direct.json().get("messages", [])
                    for raw_msg in direct_msgs:
                        self.root.after(0, self.process_incoming, raw_msg)

            except Exception:
                pass

            time.sleep(1)

    def process_incoming(self, raw_message):
        try:
            sender, target, tag, payload = raw_message.split('|', 3)
        except ValueError:
            return

        if tag == '-':
            # Nachricht entschlüsseln
            decrypted_text = self.decrypt(payload)
            self.append_text(f"@{sender}: {decrypted_text}\n")

        elif tag == 'I':
            # Einladung entschlüsseln
            decrypted_room = self.decrypt(payload)
            
            # Consent-Abfrage
            accept = messagebox.askyesno(
                "Verschlüsselte Einladung", 
                f"User '{sender}' lädt dich in den Raum '{decrypted_room}' ein.\nBeitreten und Schlüssel anwenden?"
            )
            if accept:
                self.current_room = decrypted_room
                self.last_room_msg_count = 0
                self.lbl_info.config(text=f"User: {self.username} | Raum: {self.current_room}")
                self.append_text(f"[SYSTEM] Raum gewechselt zu: {self.current_room}\n")

    def append_text(self, text):
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, text)
        self.chat_display.see(tk.END)
        self.chat_display.config(state=tk.DISABLED)

    def on_close(self):
        self.running = False
        self.root.destroy()

if __name__ == '__main__':
    root = tk.Tk()
    app = SecureChatClient(root)
    root.mainloop()