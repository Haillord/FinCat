"""
ФинКат — генератор лицензий
"""

import tkinter as tk
from tkinter import messagebox
import hmac
import hashlib
import base64
import json
from datetime import datetime, timedelta

SECRET = "finkat-offline-secret-key-2026-haillord"


def generate_key(hwid: str, days: int = None, email: str = "") -> str:
    payload = {
        "hwid": hwid,
        "email": email,
        "expires_at": (datetime.utcnow() + timedelta(days=days)).strftime("%Y-%m-%d") if days else None,
        "is_trial": days is not None,
    }
    data = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    sig = hmac.new(SECRET.encode(), data.encode(), hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(data.encode()).decode()
    return f"{token}.{sig}"


class App:
    def __init__(self, root):
        self.root = root
        root.title("ФинКат — Генератор лицензий")
        root.geometry("620x540")
        root.resizable(False, False)
        root.configure(bg="#1a1a2e")

        tk.Label(root, text="ФинКат", font=("Arial", 22, "bold"),
                 bg="#1a1a2e", fg="white").pack(pady=(20, 2))
        tk.Label(root, text="Генератор лицензионных ключей",
                 font=("Arial", 11), bg="#1a1a2e", fg="#888888").pack(pady=(0, 20))

        frame = tk.Frame(root, bg="#16213e", padx=24, pady=20)
        frame.pack(fill="x", padx=24)

        # HWID
        tk.Label(frame, text="HWID пользователя", font=("Arial", 10),
                 bg="#16213e", fg="#cccccc").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.hwid_var = tk.StringVar()
        hwid_row = tk.Frame(frame, bg="#16213e")
        hwid_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        hwid_entry = tk.Entry(hwid_row, textvariable=self.hwid_var, font=("Arial", 10),
                 bg="#0f3460", fg="white", insertbackground="white",
                 relief="flat", bd=6, width=40)
        hwid_entry.pack(side="left", fill="x", expand=True)
        tk.Button(hwid_row, text="Вставить", font=("Arial", 9),
                  bg="#374151", fg="white", relief="flat", bd=0,
                  padx=10, pady=6, cursor="hand2",
                  command=lambda: self.paste_to(self.hwid_var)).pack(side="left", padx=(6, 0))

        # Email
        tk.Label(frame, text="Email (опционально)", font=("Arial", 10),
                 bg="#16213e", fg="#cccccc").grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.email_var = tk.StringVar()
        email_row = tk.Frame(frame, bg="#16213e")
        email_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        tk.Entry(email_row, textvariable=self.email_var, font=("Arial", 10),
                 bg="#0f3460", fg="white", insertbackground="white",
                 relief="flat", bd=6, width=40).pack(side="left", fill="x", expand=True)
        tk.Button(email_row, text="Вставить", font=("Arial", 9),
                  bg="#374151", fg="white", relief="flat", bd=0,
                  padx=10, pady=6, cursor="hand2",
                  command=lambda: self.paste_to(self.email_var)).pack(side="left", padx=(6, 0))

        # Тип
        tk.Label(frame, text="Тип лицензии", font=("Arial", 10),
                 bg="#16213e", fg="#cccccc").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.type_var = tk.StringVar(value="permanent")
        type_frame = tk.Frame(frame, bg="#16213e")
        type_frame.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 4))
        for text, val in [("Бессрочная", "permanent"), ("Триал 3 дня", "trial3"), ("Триал 7 дней", "trial7")]:
            tk.Radiobutton(type_frame, text=text, variable=self.type_var, value=val,
                           bg="#16213e", fg="white", selectcolor="#0f3460",
                           activebackground="#16213e", activeforeground="white",
                           font=("Arial", 10)).pack(side="left", padx=(0, 16))

        tk.Button(root, text="Сгенерировать ключ", command=self.generate,
                  font=("Arial", 11, "bold"), bg="#4f46e5", fg="white",
                  activebackground="#4338ca", relief="flat", bd=0,
                  padx=24, pady=10, cursor="hand2").pack(pady=16)

        result_frame = tk.Frame(root, bg="#16213e", padx=16, pady=12)
        result_frame.pack(fill="x", padx=24)
        tk.Label(result_frame, text="Готовый ключ:", font=("Arial", 10),
                 bg="#16213e", fg="#cccccc").pack(anchor="w")
        key_frame = tk.Frame(result_frame, bg="#16213e")
        key_frame.pack(fill="x", pady=(6, 0))
        self.result_var = tk.StringVar()
        tk.Entry(key_frame, textvariable=self.result_var,
                 font=("Courier", 9), bg="#0f3460", fg="#00ff88",
                 insertbackground="white", relief="flat", bd=6,
                 state="readonly", width=52).pack(side="left", fill="x", expand=True)
        tk.Button(key_frame, text="Копировать", command=self.copy_key,
                  font=("Arial", 9), bg="#374151", fg="white",
                  activebackground="#4b5563", relief="flat", bd=0,
                  padx=10, pady=6, cursor="hand2").pack(side="left", padx=(8, 0))

    def paste_to(self, var):
        try:
            text = self.root.clipboard_get()
            var.set(text.strip())
        except Exception:
            messagebox.showwarning("Буфер пуст", "В буфере обмена нет текста")

    def generate(self):
        hwid = self.hwid_var.get().strip()
        if not hwid:
            messagebox.showwarning("Внимание", "Введите HWID пользователя")
            return
        email = self.email_var.get().strip()
        t = self.type_var.get()
        if t == "trial3":
            key = generate_key(hwid, days=3, email=email)
        elif t == "trial7":
            key = generate_key(hwid, days=7, email=email)
        else:
            key = generate_key(hwid, days=None, email=email)
        self.result_var.set(key)

    def copy_key(self):
        key = self.result_var.get()
        if not key:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(key)
        messagebox.showinfo("Скопировано", "Ключ скопирован в буфер обмена ✅")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()