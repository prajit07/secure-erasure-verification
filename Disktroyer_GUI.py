# disktroyer_gui.py
"""
Tkinter GUI that uses disktroyer_engine.DisktroyerEngine for operations.
By default engine runs in demo_mode (safe).
"""

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageTk, Image
import subprocess as sp
from disktroyer_engine import DisktroyerEngine


def list_disks():
    op = sp.run(["lsblk", "-dno", "name,size,tran,type"], capture_output=True)
    fop = sp.run(["grep", "disk"], input=op.stdout, capture_output=True).stdout
    sop = fop.split()
    disks = []
    temp = []
    for i in sop:
        temp.append(i.decode())
        if i.decode() == "disk":
            temp.append(i.decode())
            disks.append((temp[0], temp[1], temp[2], temp[3]))
            temp = []
    return disks


def detect_drive_type(tran):
    if not tran:
        return "HDD"
    tran = tran.lower()
    if "nvme" in tran or "ssd" in tran:
        return "SSD"
    if "sata" in tran or "ata" in tran:
        return "HDD"
    return "HDD"


class DisktroyerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Disktroyer")
        self.root.attributes("-fullscreen", True)

        self.selected_disk = None
        self.engine = DisktroyerEngine(gui=self, demo_mode=True)  # safe default

        # Load assets (ensure these image files exist)
        self.logo_photo = ImageTk.PhotoImage(Image.open("Disk_WIPE.png").resize((100, 100)))
        self.hdd_photo = ImageTk.PhotoImage(Image.open("HDD.png").resize((80, 80)))
        self.ssd_photo = ImageTk.PhotoImage(Image.open("SSD.png").resize((80, 80)))

        self.build_welcome_screen()

    def clear_screen(self):
        for w in self.root.winfo_children():
            w.destroy()

    def add_logo(self):
        frame = tk.Frame(self.root)
        tk.Label(frame, image=self.logo_photo).pack()
        frame.pack(side="top", pady=20)

    # -- Disk selection --
    def build_welcome_screen(self):
        self.clear_screen()
        self.add_logo()
        tk.Label(self.root, text="Welcome to Disktroyer", font=("Arial", 20, "bold")).pack(pady=10)
        tk.Label(self.root, text="Select your disk", font=("Arial", 16, "bold")).pack(pady=5)

        disks = list_disks()
        frame_disk = tk.Frame(self.root)
        frame_disk.pack(pady=40)

        if not disks:
            tk.Label(self.root, text="No disks detected", fg="red").pack()

        for disk in disks:
            dt = detect_drive_type(disk[2])
            icon = self.ssd_photo if dt == "SSD" else self.hdd_photo
            df = tk.Frame(frame_disk, bd=2, relief="groove", padx=10, pady=10)
            df.pack(side="left", padx=20)
            tk.Label(df, image=icon).pack()
            tk.Label(df, text=f"{disk[0]} - {disk[1]} ({dt})", font=("Arial", 12)).pack(pady=5)
            tk.Button(df, text="Select", command=lambda d=disk: self.select_disk(d)).pack(pady=5)

    def select_disk(self, disk):
        self.selected_disk = {"name": disk[0], "size": disk[1], "type": detect_drive_type(disk[2])}
        # map selected disk into engine
        self.engine.selected_disk = self.selected_disk
        self.build_level_screen()

    # -- Priority selection --
    def build_level_screen(self):
        self.clear_screen()
        self.add_logo()
        tk.Label(self.root, text=f"Disk: {self.selected_disk['name']} ({self.selected_disk['size']})",
                 font=("Arial", 18, "bold")).pack(pady=20)
        tk.Label(self.root, text="Choose Data Erasure Level", font=("Arial", 16)).pack(pady=10)

        frame = tk.Frame(self.root)
        frame.pack(pady=20)

        def start(level):
            self.engine.wipe_var.set(level)
            # engine start will show progress page itself
            self.engine.start_wiping()

        tk.Button(frame, text="Low", width=15, command=lambda: start(1)).pack(side="left", padx=20)
        tk.Button(frame, text="Medium", width=15, command=lambda: start(2)).pack(side="left", padx=20)
        tk.Button(frame, text="High", width=15, command=lambda: start(3)).pack(side="left", padx=20)

    # -- Progress page (engine will update status_text) --
    def show_progress_page(self):
        self.clear_screen()
        self.add_logo()
        tk.Label(self.root, text="Wiping in progress...", font=("Arial", 18, "bold")).pack(pady=10)
        self.status_text = tk.Text(self.root, height=15, width=80)
        self.status_text.pack(pady=8)
        self.progress_bar = ttk.Progressbar(self.root, orient="horizontal", length=400, mode="indeterminate")
        self.progress_bar.pack(pady=6)

    # -- Certificate page (read-only) --
    def show_certificate_page(self):
        self.clear_screen()
        self.add_logo()
        tk.Label(self.root, text="Certificate of Erasure", font=("Arial", 18, "bold")).pack(pady=10)
        # read-only text widget
        self.cert_info_text = tk.Text(self.root, height=25, width=80, wrap="word")
        self.cert_info_text.pack(pady=8)
        self.cert_info_text.insert(tk.END, "Certificate will appear here after the process.")
        self.cert_info_text.config(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    app = DisktroyerApp(root)
    root.mainloop()

