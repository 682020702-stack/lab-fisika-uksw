"""
app.py - Main application (satu-satunya tk.Tk)
"""

import tkinter as tk

from halaman_login import LoginFrame
from halaman_dashboard import DashboardFrame
from halaman_admin import AdminDashboardFrame


class AplikasiFSM(tk.Tk):
    WINDOW_W = 900
    WINDOW_H = 550

    def __init__(self):
        super().__init__()
        self.title("FSM UKSW - Laboratorium")
        self.minsize(900, 550)
        self.configure(bg="#ffffff")
        self._center_window(self.WINDOW_W, self.WINDOW_H)

        container = tk.Frame(self, bg="#ffffff")
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}
        for F in (LoginFrame, DashboardFrame, AdminDashboardFrame):
            page_name = F.__name__
            frame = F(parent=container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.show_frame("LoginFrame")

    def _center_window(self, w, h):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def show_frame(self, page_name):
        frame = self.frames.get(page_name)
        if frame is None:
            print(f"[ERROR] Halaman '{page_name}' tidak terdaftar.")
            return
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()


if __name__ == "__main__":
    app = AplikasiFSM()
    app.mainloop()
