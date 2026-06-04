"""
rank_songs.py
Interactive UI to review/correct song scores.
CSV paths are /pirateradio/... — translates to local mount for playback.
"""

import os
import re
import threading
import tkinter as tk
from tkinter import messagebox

import pandas as pd
import pygame

# ── Mount points ──────────────────────────────────────────────────────────────

LOCAL_DIR = next(
    (p for p in ["/pirateradio", "/run/media/njm/PIRATERADIO"] if os.path.isdir(p)),
    None
)
if LOCAL_DIR is None:
    raise RuntimeError("Cannot find PIRATERADIO mount.")

RPI_DIR       = "/pirateradio"
CSV_PATH      = os.path.join(LOCAL_DIR, "song_attributes.csv")
SAMPLE_OFFSET = 30.0

def rpi_to_local(path):
    return path.replace(RPI_DIR, LOCAL_DIR, 1)

# ── Load CSV ──────────────────────────────────────────────────────────────────

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"CSV not found: {CSV_PATH}\nRun filerename.py first.")

df = pd.read_csv(CSV_PATH, header=None, names=["file", "energy", "organics"])
df["energy"]   = pd.to_numeric(df["energy"],   errors="coerce").fillna(50).astype(int)
df["organics"] = pd.to_numeric(df["organics"], errors="coerce").fillna(50).astype(int)

pygame.mixer.init(frequency=44100)

# ── GUI ───────────────────────────────────────────────────────────────────────

class SongRater:
    def __init__(self, master, dataframe):
        self.master  = master
        self.df      = dataframe
        self.index   = 0
        self.playing = False
        self._build_ui()
        self._bind_keys()
        self.show_song()

    def _build_ui(self):
        m = self.master
        m.configure(bg="#1e1e2e")
        m.resizable(False, False)
        pad = dict(padx=16, pady=4)

        self.progress_var = tk.StringVar()
        tk.Label(m, textvariable=self.progress_var,
                 bg="#1e1e2e", fg="#888aaa", font=("Helvetica", 10)).pack(**pad)

        self.file_label = tk.Label(m, text="", wraplength=500,
                                   bg="#1e1e2e", fg="#cdd6f4",
                                   font=("Helvetica", 12, "bold"))
        self.file_label.pack(**pad)

        tk.Label(m, text="⚡  Energy  (slow ◄──► energetic)",
                 bg="#1e1e2e", fg="#89b4fa", font=("Helvetica", 10)).pack(pady=(10,0))
        self.energy_var = tk.IntVar(value=50)
        self.energy_lbl = tk.Label(m, text="50", bg="#1e1e2e", fg="#89b4fa",
                                   font=("Helvetica", 13, "bold"))
        self.energy_lbl.pack()
        tk.Scale(m, from_=0, to=100, orient=tk.HORIZONTAL, length=500,
                 variable=self.energy_var, bg="#1e1e2e", fg="#cdd6f4",
                 troughcolor="#313244", highlightthickness=0, showvalue=False,
                 command=lambda v: self.energy_lbl.config(text=str(int(float(v))))
                 ).pack(**pad)

        tk.Label(m, text="🌿  Organics  (electronic ◄──► organic)",
                 bg="#1e1e2e", fg="#a6e3a1", font=("Helvetica", 10)).pack(pady=(10,0))
        self.organics_var = tk.IntVar(value=50)
        self.organics_lbl = tk.Label(m, text="50", bg="#1e1e2e", fg="#a6e3a1",
                                     font=("Helvetica", 13, "bold"))
        self.organics_lbl.pack()
        tk.Scale(m, from_=0, to=100, orient=tk.HORIZONTAL, length=500,
                 variable=self.organics_var, bg="#1e1e2e", fg="#cdd6f4",
                 troughcolor="#313244", highlightthickness=0, showvalue=False,
                 command=lambda v: self.organics_lbl.config(text=str(int(float(v))))
                 ).pack(**pad)

        bf = tk.Frame(m, bg="#1e1e2e")
        bf.pack(pady=16)
        btn = dict(font=("Helvetica", 11), relief=tk.FLAT,
                   activebackground="#45475a", padx=12, pady=7)

        self.play_btn = tk.Button(bf, text="▶  Play  [Space]",
                                  bg="#313244", fg="#cdd6f4",
                                  command=self.toggle_play, **btn)
        self.play_btn.grid(row=0, column=0, padx=5)
        tk.Button(bf, text="◀  Back  [B]", bg="#313244", fg="#cdd6f4",
                  command=self.go_back, **btn).grid(row=0, column=1, padx=5)
        tk.Button(bf, text="Skip  [S]", bg="#313244", fg="#888aaa",
                  command=self.skip, **btn).grid(row=0, column=2, padx=5)
        tk.Button(bf, text="Save & Next  [Enter]", bg="#89b4fa", fg="#1e1e2e",
                  command=self.save_and_next, **btn).grid(row=0, column=3, padx=5)
        tk.Button(bf, text="Quit  [Q]", bg="#f38ba8", fg="#1e1e2e",
                  command=self.quit, **btn).grid(row=0, column=4, padx=5)

        tk.Label(m, text="Arrow keys adjust the focused slider",
                 bg="#1e1e2e", fg="#45475a", font=("Helvetica", 9)).pack(pady=(0,8))

    def _bind_keys(self):
        self.master.bind("<space>",  lambda e: self.toggle_play())
        self.master.bind("<Return>", lambda e: self.save_and_next())
        self.master.bind("b",        lambda e: self.go_back())
        self.master.bind("B",        lambda e: self.go_back())
        self.master.bind("s",        lambda e: self.skip())
        self.master.bind("S",        lambda e: self.skip())
        self.master.bind("q",        lambda e: self.quit())
        self.master.bind("Q",        lambda e: self.quit())

    def show_song(self):
        self.stop_playback()
        if self.index >= len(self.df):
            messagebox.showinfo("Done", "All songs reviewed!")
            self.quit()
            return
        row = self.df.iloc[self.index]
        self.progress_var.set(f"Song {self.index + 1} of {len(self.df)}")
        self.file_label.config(text=os.path.basename(row["file"]))
        e, o = int(row["energy"]), int(row["organics"])
        self.energy_var.set(e);   self.energy_lbl.config(text=str(e))
        self.organics_var.set(o); self.organics_lbl.config(text=str(o))
        self.play_btn.config(text="▶  Play  [Space]")

    def toggle_play(self):
        if self.playing: self.stop_playback()
        else:            self.start_playback()

    def start_playback(self):
        rpi_path   = self.df.iloc[self.index]["file"]
        local_path = rpi_to_local(rpi_path)
        if not os.path.exists(local_path):
            messagebox.showerror("Not found", f"File not found:\n{local_path}")
            return
        def _play():
            try:
                pygame.mixer.music.load(local_path)
                pygame.mixer.music.play(start=SAMPLE_OFFSET)
            except Exception as e:
                messagebox.showerror("Playback error", str(e))
        self.playing = True
        self.play_btn.config(text="■  Stop  [Space]")
        threading.Thread(target=_play, daemon=True).start()

    def stop_playback(self):
        self.playing = False
        try: pygame.mixer.music.stop()
        except Exception: pass
        self.play_btn.config(text="▶  Play  [Space]")

    def _commit(self):
        self.df.at[self.index, "energy"]   = self.energy_var.get()
        self.df.at[self.index, "organics"] = self.organics_var.get()

    def _save_csv(self):
        self.df.to_csv(CSV_PATH, index=False, header=False)

    def save_and_next(self):
        self._commit(); self._save_csv()
        self.index += 1; self.show_song()

    def skip(self):
        self.index += 1; self.show_song()

    def go_back(self):
        if self.index > 0:
            self.index -= 1; self.show_song()

    def quit(self):
        self._save_csv(); self.master.quit()

root = tk.Tk()
root.title("Pirate Radio — Song Rater")
SongRater(root, df)
root.mainloop()
