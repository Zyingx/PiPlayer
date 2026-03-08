"""PiPlayer v3.0 — Music Player with Global Queue"""

import tkinter as tki
from tkinter import ttk, filedialog
import tkinter.messagebox
import os, random, time, threading
import pygame
from mutagen import File as MutagenFile
import spotify_tab

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(BASE_DIR, "Music")
ICON_PATH = os.path.join(BASE_DIR, "Logo & Stuff", "PiPlayer.ico")

# ── Colors ────────────────────────────────────────────────────────
BG      = "#08080e"
BG2     = "#0e0e1a"
BG3     = "#131326"
BG4     = "#1a1a36"
BG5     = "#161630"
GRN     = "#1DB954"
GRN2    = "#1ed760"
GRN_BG  = "#0d2e1a"
PRP     = "#7c5cfc"
TX1     = "#f0f0f5"
TX2     = "#9090a8"
TX3     = "#505068"
BRD     = "#1e1e3a"
BRD2    = "#2a2a50"
PGB     = "#1a1a30"
RED     = "#ff4757"

# ── Fonts ─────────────────────────────────────────────────────────
FH = ("Segoe UI", 10, "bold")
FS = ("Segoe UI", 9)
FT = ("Segoe UI", 8)
FL = ("Segoe UI", 10)
FB = ("Segoe UI", 14, "bold")
FN = ("Segoe UI", 13, "bold")   # now-playing title
FA = ("Segoe UI", 10)           # now-playing artist
FTM = ("Segoe UI Semibold", 9)  # time
FLG = ("Segoe UI", 15, "bold")  # logo

# ═══════════════════════════════════════════════════════════════════
#  STATE
# ═══════════════════════════════════════════════════════════════════
class State:
    def __init__(self):
        self.queue = []       # [{source, title, artist, file?, track_data?}]
        self.qi = -1          # current queue index
        self.local_files = [] # full paths
        self.local_names = [] # display names
        self.playing = False
        self.paused = False
        self.shuffle = False
        self.repeat = 0       # 0=off, 1=all, 2=one
        self.volume = 0.7
        self.duration = 0
        self.elapsed = 0
        self._t0 = 0
        self._off = 0

st = State()

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def fmt_time(s):
    if s <= 0: return "0:00"
    return f"{int(s//60)}:{int(s%60):02d}"

def get_dur(fp):
    try:
        a = MutagenFile(fp)
        if a and a.info: return a.info.length
    except: pass
    return 0

def parse_name(fn):
    return os.path.splitext(fn)[0].replace("_", " ")

def scan_music():
    exts = (".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma")
    if not os.path.isdir(MUSIC_DIR): return []
    return [os.path.join(MUSIC_DIR, f) for f in sorted(os.listdir(MUSIC_DIR))
            if os.path.splitext(f)[1].lower() in exts]

def card(par, bg=BG3, brd=BRD):
    o = tki.Frame(par, bg=brd, padx=1, pady=1)
    i = tki.Frame(o, bg=bg); i.pack(fill="both", expand=True)
    return o, i

def hover(w, nb, hb, nf=TX1, hf=None):
    hf = hf or nf
    w.bind("<Enter>", lambda e: w.configure(bg=hb, fg=hf))
    w.bind("<Leave>", lambda e: w.configure(bg=nb, fg=nf))

# ═══════════════════════════════════════════════════════════════════
#  QUEUE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

def add_local_to_queue(index):
    """Add a local track to queue by index."""
    if index < 0 or index >= len(st.local_files): return
    fp = st.local_files[index]
    name = st.local_names[index]
    if " - " in name:
        parts = name.split(" - ", 1)
        artist, title = parts[0].strip(), parts[1].strip()
    else:
        title, artist = name, "Local"
    st.queue.append({"source": "local", "title": title, "artist": artist, "file": fp})
    render_queue()

def add_spotify_to_queue(title, artist, track_data):
    """Add a Spotify track to queue (called by spotify_tab)."""
    st.queue.append({"source": "spotify", "title": title, "artist": artist,
                     "track_data": track_data})
    render_queue()

def remove_from_queue(idx):
    if 0 <= idx < len(st.queue):
        st.queue.pop(idx)
        if st.qi >= idx and st.qi > 0:
            st.qi -= 1
        elif st.qi >= len(st.queue):
            st.qi = len(st.queue) - 1
        render_queue()

def clear_queue():
    st.queue.clear()
    st.qi = -1
    stop_playback()
    render_queue()

# ═══════════════════════════════════════════════════════════════════
#  PLAYBACK ENGINE
# ═══════════════════════════════════════════════════════════════════

def play_from_queue(idx):
    """Play item at queue index."""
    if idx < 0 or idx >= len(st.queue): return
    st.qi = idx
    item = st.queue[idx]

    if item["source"] == "local":
        _play_local(item)
    elif item["source"] == "spotify":
        if spotify_tab.PREMIUM_ENABLED and spotify_tab.sp:
            _play_spotify(item)
        else:
            # Can't play Spotify without Premium — skip to next
            tkinter.messagebox.showinfo("Premium Required",
                f"Cannot play \"{item['title']}\" — Spotify Premium needed.\n"
                "Skipping to next track...")
            render_queue()
            update_now_playing_ui()
            root.after(500, play_next)
            return
    render_queue()
    update_now_playing_ui()

def _play_local(item):
    try:
        pygame.mixer.music.load(item["file"])
        pygame.mixer.music.set_volume(st.volume)
        pygame.mixer.music.play()
        st.playing = True
        st.paused = False
        st.duration = get_dur(item["file"])
        st._t0 = time.time()
        st._off = 0
        st.elapsed = 0
        _start_tick()
    except Exception as e:
        tkinter.messagebox.showerror("Error", f"Could not play:\n{item['title']}\n{e}")

def _play_spotify(item):
    try:
        sp = spotify_tab.sp
        devices = sp.devices()
        if not devices['devices']:
            tkinter.messagebox.showwarning("No Device", "Open Spotify app first.")
            return
        active = None
        for d in devices['devices']:
            if d['is_active']: active = d['id']; break
        if not active:
            active = devices['devices'][0]['id']
        sp.start_playback(device_id=active, uris=[item['track_data']['uri']])
        st.playing = True
        st.paused = False
        st.duration = item['track_data'].get('duration_ms', 0) / 1000
        st._t0 = time.time()
        st._off = 0
        st.elapsed = 0
        _start_tick()
    except Exception as e:
        tkinter.messagebox.showerror("Playback Error", str(e))

def toggle_play():
    if st.qi == -1:
        if st.queue: play_from_queue(0)
        return
    if st.paused:
        pygame.mixer.music.unpause()
        st.paused = False; st.playing = True
        st._t0 = time.time()
        _start_tick()
    elif st.playing:
        pygame.mixer.music.pause()
        st.paused = True; st.playing = False
        st._off = st.elapsed
    else:
        play_from_queue(st.qi)
    _update_btn()

def stop_playback():
    pygame.mixer.music.stop()
    st.playing = False; st.paused = False
    st.elapsed = 0; st._off = 0
    _update_btn()
    _draw_progress(0, st.duration)
    lbl_cur.config(text="0:00")

def play_next():
    if not st.queue: return
    if st.repeat == 2:
        play_from_queue(st.qi); return
    if st.shuffle:
        nxt = random.randint(0, len(st.queue) - 1)
    else:
        nxt = (st.qi + 1) % len(st.queue)
    if nxt == 0 and st.repeat == 0 and not st.shuffle and st.qi == len(st.queue) - 1:
        stop_playback(); return
    play_from_queue(nxt)

def play_prev():
    if not st.queue: return
    if st.elapsed > 3:
        play_from_queue(st.qi); return
    nxt = (st.qi - 1) % len(st.queue)
    play_from_queue(nxt)

def toggle_shuffle():
    st.shuffle = not st.shuffle
    shuf_btn.config(fg=GRN if st.shuffle else TX3)

def toggle_repeat():
    st.repeat = (st.repeat + 1) % 3
    syms = ["🔁", "🔁", "🔂"]
    cols = [TX3, GRN, PRP]
    rep_btn.config(text=syms[st.repeat], fg=cols[st.repeat])

def set_vol(v):
    st.volume = float(v) / 100
    pygame.mixer.music.set_volume(st.volume)
    v_pct.config(text=f"{int(float(v))}%")
    if st.volume == 0: v_icon.config(text="🔇")
    elif st.volume < 0.4: v_icon.config(text="🔉")
    else: v_icon.config(text="🔊")

def toggle_mute():
    if st.volume > 0:
        st._pv = st.volume; st.volume = 0; vol_sl.set(0)
    else:
        st.volume = getattr(st, '_pv', 0.7); vol_sl.set(st.volume * 100)
    pygame.mixer.music.set_volume(st.volume)
    set_vol(st.volume * 100)

def seek(ev):
    if st.duration <= 0 or not st.playing: return
    pct = max(0, min(1, ev.x / prog_bar.winfo_width()))
    pos = pct * st.duration
    if st.qi >= 0 and st.queue[st.qi]["source"] == "local":
        try:
            pygame.mixer.music.load(st.queue[st.qi]["file"])
            pygame.mixer.music.play(start=pos)
            pygame.mixer.music.set_volume(st.volume)
            st._t0 = time.time(); st._off = pos; st.elapsed = pos
        except: pass

# ── Progress tick ─────────────────────────────────────────────────
def _start_tick():
    def tick():
        if st.playing and not st.paused:
            st.elapsed = st._off + (time.time() - st._t0)
            _draw_progress(st.elapsed, st.duration)
            lbl_cur.config(text=fmt_time(st.elapsed))
            lbl_tot.config(text=fmt_time(st.duration))
            if not pygame.mixer.music.get_busy() and st.playing:
                st.playing = False
                play_next()
                return
        if st.playing or st.paused:
            root.after(200, tick)
    tick()

def _update_btn():
    play_btn.config(text="⏸" if st.playing else "▶")

# ═══════════════════════════════════════════════════════════════════
#  UI UPDATE
# ═══════════════════════════════════════════════════════════════════

def update_now_playing_ui():
    if st.qi < 0 or st.qi >= len(st.queue):
        np_title.config(text="No track selected")
        np_artist.config(text="PiPlayer")
        lbl_cur.config(text="0:00"); lbl_tot.config(text="0:00")
        return
    item = st.queue[st.qi]
    src_icon = "🎵" if item["source"] == "local" else "🎧"
    np_title.config(text=f"{src_icon}  {item['title']}")
    np_artist.config(text=item["artist"])
    lbl_tot.config(text=fmt_time(st.duration))

def _draw_progress(cur, tot):
    prog_bar.delete("all")
    w = prog_bar.winfo_width()
    h = prog_bar.winfo_height()
    prog_bar.create_rectangle(0, 0, w, h, fill=PGB, outline="")
    if tot > 0:
        fw = min(w, max(0, (cur/tot) * w))
        if fw > 0:
            prog_bar.create_rectangle(0, 0, fw, h, fill=GRN, outline="")
            if fw > 4:
                cy = h / 2
                prog_bar.create_oval(fw-5, cy-5, fw+5, cy+5, fill=GRN2, outline="")

def render_queue():
    q_list.delete(0, tki.END)
    for i, item in enumerate(st.queue):
        icon = "🎵" if item["source"] == "local" else "🎧"
        prefix = " ▶ " if i == st.qi else f" {i+1}. "
        q_list.insert(tki.END, f"{prefix}{icon} {item['title']}  —  {item['artist']}")
        if i == st.qi:
            q_list.itemconfig(i, fg=GRN)
    q_count.config(text=f"{len(st.queue)}")

def load_local_tracks():
    st.local_files = scan_music()
    st.local_names = [parse_name(os.path.basename(f)) for f in st.local_files]
    local_list.delete(0, tki.END)
    for n in st.local_names:
        local_list.insert(tki.END, f"  {n}")
    local_count.config(text=f"{len(st.local_files)} tracks")

# ═══════════════════════════════════════════════════════════════════
#  WINDOW
# ═══════════════════════════════════════════════════════════════════
root = tki.Tk()
root.title("PiPlayer v3.0")
try: root.iconbitmap(ICON_PATH)
except: pass
root.geometry("960x620")
root.minsize(800, 500)
root.configure(bg=BG)
root.option_add("*Font", ("Segoe UI", 10))

# ── Status bar (pack first = always at bottom) ───────────────────
status = tki.Frame(root, bg=BG4, height=22)
status.pack(side="bottom", fill="x")
status.pack_propagate(False)
tki.Label(status, text="  PiPlayer v3.0  ·  Local + Spotify",
    font=FT, bg=BG4, fg=TX3).pack(side="left", padx=6)
tki.Label(status, text="♫ Ready  ", font=FT, bg=BG4, fg=TX3).pack(side="right", padx=6)

# ═══════════════════════════════════════════════════════════════════
#  BOTTOM PLAYER BAR
# ═══════════════════════════════════════════════════════════════════
btm = tki.Frame(root, bg=BG2, height=90)
btm.pack(side="bottom", fill="x")
btm.pack_propagate(False)

# Progress bar (top of bottom bar)
prog_bar = tki.Canvas(btm, height=6, bg=PGB, highlightthickness=0, bd=0, cursor="hand2")
prog_bar.pack(fill="x", side="top")
prog_bar.bind("<Button-1>", seek)

# Bottom content
btm_inner = tki.Frame(btm, bg=BG2, padx=16)
btm_inner.pack(fill="both", expand=True)

# Left: track info
info_frame = tki.Frame(btm_inner, bg=BG2, width=260)
info_frame.pack(side="left", fill="y", pady=8)
info_frame.pack_propagate(False)

np_title = tki.Label(info_frame, text="No track selected",
    font=FN, bg=BG2, fg=TX1, anchor="w")
np_title.pack(fill="x")

np_artist = tki.Label(info_frame, text="PiPlayer",
    font=FA, bg=BG2, fg=GRN, anchor="w")
np_artist.pack(fill="x", pady=(2, 0))

# Center: controls
ctrl_frame = tki.Frame(btm_inner, bg=BG2)
ctrl_frame.pack(side="left", expand=True, pady=8)

ctrl_row = tki.Frame(ctrl_frame, bg=BG2)
ctrl_row.pack()

def mkbtn(par, txt, cmd, sz=14, fg=TX1, w=2):
    b = tki.Button(par, text=txt, command=cmd, bg=BG4, fg=fg,
        font=("Segoe UI", sz), relief=tki.FLAT, cursor="hand2",
        width=w, padx=2, pady=0, borderwidth=0, highlightthickness=0,
        activebackground=GRN, activeforeground=TX1)
    b.pack(side="left", padx=4)
    hover(b, BG4, BRD2, fg, TX1)
    return b

shuf_btn = mkbtn(ctrl_row, "🔀", toggle_shuffle, 12, TX3)
mkbtn(ctrl_row, "⏮", play_prev, 14)
play_btn = mkbtn(ctrl_row, "▶", toggle_play, 18, BG, 3)
play_btn.config(bg=GRN, activebackground=GRN2)
hover(play_btn, GRN, GRN2, BG, BG)
mkbtn(ctrl_row, "⏭", play_next, 14)
rep_btn = mkbtn(ctrl_row, "🔁", toggle_repeat, 12, TX3)
mkbtn(ctrl_row, "⏹", stop_playback, 12, TX3)

# Time labels
time_row = tki.Frame(ctrl_frame, bg=BG2)
time_row.pack(pady=(4, 0))
lbl_cur = tki.Label(time_row, text="0:00", font=FTM, bg=BG2, fg=TX2)
lbl_cur.pack(side="left")
tki.Label(time_row, text="  /  ", font=FT, bg=BG2, fg=TX3).pack(side="left")
lbl_tot = tki.Label(time_row, text="0:00", font=FTM, bg=BG2, fg=TX3)
lbl_tot.pack(side="left")

# Right: volume
vol_frame = tki.Frame(btm_inner, bg=BG2, width=170)
vol_frame.pack(side="right", fill="y", pady=12)
vol_frame.pack_propagate(False)

vol_row = tki.Frame(vol_frame, bg=BG2)
vol_row.pack(fill="x")

v_icon = tki.Label(vol_row, text="🔊", font=("Segoe UI", 12),
    bg=BG2, fg=TX2, cursor="hand2")
v_icon.pack(side="left")
v_icon.bind("<Button-1>", lambda e: toggle_mute())

vol_sl = tki.Scale(vol_row, from_=0, to=100, orient=tki.HORIZONTAL,
    command=set_vol, bg=BG2, fg=GRN, troughcolor=PGB,
    activebackground=GRN2, highlightthickness=0, borderwidth=0,
    sliderrelief=tki.FLAT, length=80, sliderlength=12, showvalue=False)
vol_sl.set(70)
vol_sl.pack(side="left", padx=(6, 6))

v_pct = tki.Label(vol_row, text="70%", font=FT, bg=BG2, fg=TX3)
v_pct.pack(side="left")

# ═══════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════
hdr = tki.Frame(root, bg=BG2, height=48)
hdr.pack(side="top", fill="x")
hdr.pack_propagate(False)

hdr_in = tki.Frame(hdr, bg=BG2)
hdr_in.pack(fill="x", padx=18)
tki.Label(hdr_in, text="🎧  PiPlayer", font=FLG, bg=BG2, fg=TX1).pack(side="left", pady=8)
tki.Label(hdr_in, text="v3.0", font=FT, bg=GRN_BG, fg=GRN, padx=8, pady=2).pack(side="right", pady=12)

tki.Frame(root, bg=BRD, height=1).pack(side="top", fill="x")

# ═══════════════════════════════════════════════════════════════════
#  MAIN CONTENT = Browse Tabs (left) + Queue (right)
# ═══════════════════════════════════════════════════════════════════
main = tki.Frame(root, bg=BG)
main.pack(fill="both", expand=True)

# ── QUEUE PANEL (right) ──────────────────────────────────────────
q_panel = tki.Frame(main, bg=BG, width=280)
q_panel.pack(side="right", fill="y", padx=(0, 10), pady=10)
q_panel.pack_propagate(False)

q_outer, q_card = card(q_panel)
q_outer.pack(fill="both", expand=True)

q_hdr = tki.Frame(q_card, bg=BG4)
q_hdr.pack(fill="x")
tki.Label(q_hdr, text="  ♪  PLAY QUEUE", font=FH, bg=BG4, fg=GRN).pack(side="left", pady=8, padx=6)
q_count = tki.Label(q_hdr, text="0", font=FT, bg=BG4, fg=TX3)
q_count.pack(side="right", padx=8)

# Queue action buttons
q_btn_row = tki.Frame(q_card, bg=BG3, padx=6, pady=4)
q_btn_row.pack(fill="x")

def add_all_local():
    for i in range(len(st.local_files)):
        add_local_to_queue(i)
tki.Button(q_btn_row, text="+ All Local", command=add_all_local,
    bg=BG4, fg=TX2, font=FT, padx=6, pady=1, relief=tki.FLAT,
    cursor="hand2", borderwidth=0, highlightthickness=0).pack(side="left", padx=2)

tki.Button(q_btn_row, text="Clear", command=clear_queue,
    bg=BG4, fg=RED, font=FT, padx=6, pady=1, relief=tki.FLAT,
    cursor="hand2", borderwidth=0, highlightthickness=0).pack(side="right", padx=2)

def remove_selected():
    sel = q_list.curselection()
    if sel: remove_from_queue(int(sel[0]))
tki.Button(q_btn_row, text="Remove", command=remove_selected,
    bg=BG4, fg=TX3, font=FT, padx=6, pady=1, relief=tki.FLAT,
    cursor="hand2", borderwidth=0, highlightthickness=0).pack(side="right", padx=2)

# Queue listbox
q_lf = tki.Frame(q_card, bg=BG3)
q_lf.pack(fill="both", expand=True, padx=4, pady=4)

q_sb = tki.Scrollbar(q_lf, bg=BG4, troughcolor=BG3,
    highlightthickness=0, borderwidth=0)
q_sb.pack(side="right", fill="y")

q_list = tki.Listbox(q_lf, bg=BG3, fg=TX1, font=FL, relief=tki.FLAT,
    borderwidth=0, selectbackground=GRN_BG, selectforeground=GRN,
    highlightthickness=0, activestyle="none", yscrollcommand=q_sb.set)
q_list.pack(fill="both", expand=True)
q_sb.config(command=q_list.yview)
q_list.bind("<Double-Button-1>", lambda e: (
    play_from_queue(int(q_list.curselection()[0])) if q_list.curselection() else None))

# ── BROWSE PANEL (left) ──────────────────────────────────────────
browse = tki.Frame(main, bg=BG)
browse.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=10)

# Tab bar
tab_bar = tki.Frame(browse, bg=BG)
tab_bar.pack(fill="x", pady=(0, 8))

cur_tab = tki.StringVar(value="local")
local_frame = tki.Frame(browse, bg=BG)
spotify_frame = tki.Frame(browse, bg=BG)

def switch_tab(name):
    cur_tab.set(name)
    if name == "local":
        spotify_frame.pack_forget()
        local_frame.pack(fill="both", expand=True)
        t_local.config(bg=GRN_BG, fg=GRN)
        t_spot.config(bg=BG2, fg=TX3)
    else:
        local_frame.pack_forget()
        spotify_frame.pack(fill="both", expand=True)
        t_local.config(bg=BG2, fg=TX3)
        t_spot.config(bg=GRN_BG, fg=GRN)

t_local = tki.Button(tab_bar, text="🎵 Local Music",
    command=lambda: switch_tab("local"),
    bg=GRN_BG, fg=GRN, font=("Segoe UI", 10, "bold"),
    relief=tki.FLAT, cursor="hand2", padx=14, pady=5,
    borderwidth=0, highlightthickness=0)
t_local.pack(side="left", padx=(0, 4))

t_spot = tki.Button(tab_bar, text="🎧 Spotify",
    command=lambda: switch_tab("spotify"),
    bg=BG2, fg=TX3, font=("Segoe UI", 10, "bold"),
    relief=tki.FLAT, cursor="hand2", padx=14, pady=5,
    borderwidth=0, highlightthickness=0)
t_spot.pack(side="left")

# Show local tab by default
local_frame.pack(fill="both", expand=True)

# ── LOCAL TAB ─────────────────────────────────────────────────────
loc_outer, loc_card = card(local_frame)
loc_outer.pack(fill="both", expand=True)

loc_hdr = tki.Frame(loc_card, bg=BG4)
loc_hdr.pack(fill="x")
tki.Label(loc_hdr, text="  🎵  LOCAL LIBRARY", font=FH,
    bg=BG4, fg=GRN).pack(side="left", pady=8, padx=6)
local_count = tki.Label(loc_hdr, text="0 tracks", font=FT, bg=BG4, fg=TX3)
local_count.pack(side="right", padx=8)

def add_files():
    files = filedialog.askopenfilenames(title="Add Music Files",
        filetypes=[("Audio", "*.mp3 *.wav *.ogg *.flac *.aac *.m4a"), ("All", "*.*")])
    for f in files:
        if f not in st.local_files:
            st.local_files.append(f)
            st.local_names.append(parse_name(os.path.basename(f)))
    load_local_tracks()

add_b = tki.Button(loc_hdr, text="+ Add", command=add_files,
    bg=BG4, fg=TX2, font=FT, padx=6, pady=1, relief=tki.FLAT,
    cursor="hand2", borderwidth=0, highlightthickness=0)
add_b.pack(side="right", padx=4, pady=6)

# Help text
loc_help = tki.Frame(loc_card, bg=BG3, padx=10, pady=4)
loc_help.pack(fill="x")
tki.Label(loc_help, text="Double-click to add to queue",
    font=FT, bg=BG3, fg=TX3).pack(anchor="w")

loc_lf = tki.Frame(loc_card, bg=BG3)
loc_lf.pack(fill="both", expand=True, padx=4, pady=4)

loc_sb = tki.Scrollbar(loc_lf, bg=BG4, troughcolor=BG3,
    highlightthickness=0, borderwidth=0)
loc_sb.pack(side="right", fill="y")

local_list = tki.Listbox(loc_lf, bg=BG3, fg=TX1, font=FL, relief=tki.FLAT,
    borderwidth=0, selectbackground=GRN_BG, selectforeground=GRN,
    highlightthickness=0, activestyle="none", yscrollcommand=loc_sb.set)
local_list.pack(fill="both", expand=True)
loc_sb.config(command=local_list.yview)

def on_local_dblclick(ev):
    sel = local_list.curselection()
    if sel:
        add_local_to_queue(int(sel[0]))
local_list.bind("<Double-Button-1>", on_local_dblclick)

# ── SPOTIFY TAB ───────────────────────────────────────────────────
spot_colors = {
    "BG_CARD": BG3, "BG_ELEVATED": BG4, "BG_INPUT": BG5,
    "ACCENT": GRN, "ACCENT_HOVER": GRN2, "ACCENT_BG": GRN_BG,
    "BORDER": BRD, "TEXT_PRIMARY": TX1, "TEXT_SECONDARY": TX2, "TEXT_MUTED": TX3,
    "PROGRESS_BG": PGB,
}
spot_fonts = {"FONT_HEADER": FH, "FONT_SMALL": FS, "FONT_TINY": FT, "FONT_LISTBOX": FL,
    "FONT_TITLE": FN, "FONT_ARTIST": FA, "FONT_TIME": FTM}
spotify_tab.build_spotify_browse(spotify_frame, spot_colors, spot_fonts, root, add_spotify_to_queue)

# ═══════════════════════════════════════════════════════════════════
#  MENU BAR
# ═══════════════════════════════════════════════════════════════════
menubar = tki.Menu(root, bg=BG2, fg=TX1, activebackground=GRN,
    activeforeground=TX1, relief=tki.FLAT, borderwidth=0)
root.config(menu=menubar)

fmenu = tki.Menu(menubar, tearoff=0, bg=BG2, fg=TX1,
    activebackground=GRN, activeforeground=TX1)
menubar.add_cascade(label=" ♫ File ", menu=fmenu)
fmenu.add_command(label="  Add Files...", command=add_files)
fmenu.add_separator()
fmenu.add_command(label="  Exit", command=root.destroy)

hmenu = tki.Menu(menubar, tearoff=0, bg=BG2, fg=TX1,
    activebackground=GRN, activeforeground=TX1)
menubar.add_cascade(label=" Help ", menu=hmenu)
hmenu.add_command(label="  About", command=lambda: tkinter.messagebox.showinfo(
    "About PiPlayer",
    "PiPlayer v3.0\n\nLocal + Spotify Music Player\n"
    "Global queue with mixed playback.\n\nOriginally created in 2020."))

# ═══════════════════════════════════════════════════════════════════
#  KEYBOARD
# ═══════════════════════════════════════════════════════════════════
def on_key(ev):
    if ev.keysym == "space": toggle_play()
    elif ev.keysym == "Right": play_next()
    elif ev.keysym == "Left": play_prev()
    elif ev.keysym == "Up": vol_sl.set(min(100, vol_sl.get()+5)); set_vol(vol_sl.get())
    elif ev.keysym == "Down": vol_sl.set(max(0, vol_sl.get()-5)); set_vol(vol_sl.get())
root.bind("<Key>", on_key)

# ═══════════════════════════════════════════════════════════════════
#  INIT
# ═══════════════════════════════════════════════════════════════════
load_local_tracks()
set_vol(70)

def on_close():
    pygame.mixer.music.stop()
    pygame.mixer.quit()
    root.destroy()
root.protocol("WM_DELETE_WINDOW", on_close)

root.mainloop()
