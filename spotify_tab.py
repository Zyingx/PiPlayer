"""
PiPlayer — Spotify Browse Tab
Browsing & search only. Tracks are added to the global queue.
Set PREMIUM_ENABLED = True when you have Spotify Premium.
"""

import tkinter as tki
import tkinter.messagebox
import os
import threading

PREMIUM_ENABLED = False

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    from spotify_config import (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
                                SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPE)
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

sp = None
spotify_connected = False
_playlists_data = []
_tracks_data = []


def build_spotify_browse(parent, colors, fonts, root_ref, add_to_queue_fn):
    """
    Build Spotify browse UI inside parent.
    add_to_queue_fn(title, artist, track_data) adds a Spotify track to the global queue.
    """
    global sp, spotify_connected

    C = colors  # shorthand
    BG_CARD, BG_ELV, BG_INP = C["BG_CARD"], C["BG_ELEVATED"], C["BG_INPUT"]
    ACCENT, ACCENT_HV, ACCENT_BG = C["ACCENT"], C["ACCENT_HOVER"], C["ACCENT_BG"]
    BORDER = C["BORDER"]
    TX1, TX2, TX3 = C["TEXT_PRIMARY"], C["TEXT_SECONDARY"], C["TEXT_MUTED"]
    SP_GREEN = "#1DB954"
    SP_DARK = "#0a0a14"

    F_HDR = fonts["FONT_HEADER"]
    F_SM = fonts["FONT_SMALL"]
    F_TINY = fonts["FONT_TINY"]
    F_LIST = fonts["FONT_LISTBOX"]

    def card(par, bg=BG_CARD):
        o = tki.Frame(par, bg=BORDER, padx=1, pady=1)
        i = tki.Frame(o, bg=bg)
        i.pack(fill="both", expand=True)
        return o, i

    def hover(w, nbg, hbg, nfg=TX1, hfg=None):
        hfg = hfg or nfg
        w.bind("<Enter>", lambda e: w.configure(bg=hbg, fg=hfg))
        w.bind("<Leave>", lambda e: w.configure(bg=nbg, fg=nfg))

    # ── Connection ────────────────────────────────────────────────
    conn_o, conn = card(parent, SP_DARK)
    conn_o.pack(fill="x", pady=(0, 8))

    conn_body = tki.Frame(conn, bg=SP_DARK, padx=12, pady=10)
    conn_body.pack(fill="x")

    def do_connect():
        global sp, spotify_connected
        if not SPOTIPY_AVAILABLE:
            tkinter.messagebox.showerror("Error", "spotipy not installed.\nRun: pip install spotipy")
            return
        try:
            cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spotify_cache")
            auth = SpotifyOAuth(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI, scope=SPOTIFY_SCOPE,
                cache_path=cache, open_browser=True)
            sp = spotipy.Spotify(auth_manager=auth)
            user = sp.current_user()
            spotify_connected = True
            status_lbl.config(text=f"✓ {user['display_name']}", fg=SP_GREEN)
            conn_btn.config(text="Connected", bg=SP_GREEN, state="disabled")
            _load_playlists()
        except Exception as e:
            tkinter.messagebox.showerror("Error", f"Connection failed:\n{e}")

    conn_btn = tki.Button(conn_body, text="🎧 Connect Spotify",
        command=lambda: threading.Thread(target=do_connect, daemon=True).start(),
        bg=SP_GREEN, fg=TX1, font=F_SM, padx=12, pady=4,
        relief=tki.FLAT, cursor="hand2", borderwidth=0, highlightthickness=0)
    conn_btn.pack(side="left")

    status_lbl = tki.Label(conn_body, text="Not connected",
        bg=SP_DARK, fg=TX3, font=F_TINY)
    status_lbl.pack(side="left", padx=(10, 0))

    if not PREMIUM_ENABLED:
        tki.Label(conn_body, text="Browse Only (no Premium)",
            bg=SP_DARK, fg="#997700", font=F_TINY).pack(side="right")

    # ── Search ────────────────────────────────────────────────────
    srch_o, srch = card(parent)
    srch_o.pack(fill="x", pady=(0, 8))

    srch_body = tki.Frame(srch, bg=BG_CARD, padx=12, pady=8)
    srch_body.pack(fill="x")

    tki.Label(srch_body, text="SEARCH", font=("Segoe UI", 8, "bold"),
        bg=BG_CARD, fg=TX3).pack(anchor="w")

    srch_row = tki.Frame(srch_body, bg=BG_CARD)
    srch_row.pack(fill="x", pady=(4, 0))

    srch_var = tki.StringVar()
    srch_ent = tki.Entry(srch_row, textvariable=srch_var,
        bg=BG_INP, fg=TX1, font=F_LIST, relief=tki.FLAT,
        insertbackground=SP_GREEN, borderwidth=0,
        highlightthickness=1, highlightcolor=SP_GREEN, highlightbackground=BORDER)
    srch_ent.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 6))

    def do_search():
        if not spotify_connected or not sp:
            tkinter.messagebox.showwarning("Not Connected", "Connect first.")
            return
        q = srch_var.get().strip()
        if not q:
            return
        try:
            track_box.delete(0, tki.END)
            _tracks_data.clear()
            res = sp.search(q=q, type='track', limit=20)
            for t in res['tracks']['items']:
                art = ", ".join([a['name'] for a in t['artists']])
                track_box.insert(tki.END, f"  {t['name']}  —  {art}")
                _tracks_data.append(t)
            tr_count.config(text=f"{len(_tracks_data)} results")
        except Exception as e:
            print(f"Search error: {e}")

    srch_ent.bind("<Return>", lambda e: do_search())
    tki.Button(srch_row, text="Search", command=do_search,
        bg=SP_GREEN, fg=TX1, font=F_TINY, padx=10, pady=3,
        relief=tki.FLAT, cursor="hand2", borderwidth=0, highlightthickness=0
    ).pack(side="right")

    # ── Playlists ─────────────────────────────────────────────────
    pl_o, pl_c = card(parent)
    pl_o.pack(fill="both", expand=True, pady=(0, 8))

    pl_hdr = tki.Frame(pl_c, bg=SP_DARK)
    pl_hdr.pack(fill="x")
    tki.Label(pl_hdr, text="  ♪ PLAYLISTS", font=F_HDR,
        bg=SP_DARK, fg=SP_GREEN).pack(side="left", pady=6, padx=6)
    pl_count = tki.Label(pl_hdr, text="0", font=F_TINY, bg=SP_DARK, fg=TX3)
    pl_count.pack(side="right", padx=8)

    pl_frame = tki.Frame(pl_c, bg=BG_CARD)
    pl_frame.pack(fill="both", expand=True, padx=4, pady=4)
    pl_sb = tki.Scrollbar(pl_frame, bg=BG_ELV, troughcolor=BG_CARD,
        highlightthickness=0, borderwidth=0)
    pl_sb.pack(side="right", fill="y")
    pl_box = tki.Listbox(pl_frame, bg=BG_CARD, fg=TX1, font=F_LIST, relief=tki.FLAT,
        borderwidth=0, selectbackground=ACCENT_BG, selectforeground=ACCENT,
        highlightthickness=0, activestyle="none", yscrollcommand=pl_sb.set)
    pl_box.pack(fill="both", expand=True)
    pl_sb.config(command=pl_box.yview)

    # ── Tracks ────────────────────────────────────────────────────
    tr_o, tr_c = card(parent)
    tr_o.pack(fill="both", expand=True)

    tr_hdr = tki.Frame(tr_c, bg=SP_DARK)
    tr_hdr.pack(fill="x")
    tki.Label(tr_hdr, text="  ♬ TRACKS", font=F_HDR,
        bg=SP_DARK, fg=SP_GREEN).pack(side="left", pady=6, padx=6)
    tr_count = tki.Label(tr_hdr, text="0", font=F_TINY, bg=SP_DARK, fg=TX3)
    tr_count.pack(side="right", padx=8)

    # Add to queue button
    def add_selected_to_queue():
        sel = track_box.curselection()
        if not sel:
            return
        t = _tracks_data[int(sel[0])]
        art = ", ".join([a['name'] for a in t['artists']])
        add_to_queue_fn(t['name'], art, t)

    tki.Button(tr_hdr, text="+ Queue", command=add_selected_to_queue,
        bg=SP_DARK, fg=SP_GREEN, font=F_TINY, padx=6, pady=1,
        relief=tki.FLAT, cursor="hand2", borderwidth=0, highlightthickness=0
    ).pack(side="right", padx=4)

    tr_frame = tki.Frame(tr_c, bg=BG_CARD)
    tr_frame.pack(fill="both", expand=True, padx=4, pady=4)
    tr_sb = tki.Scrollbar(tr_frame, bg=BG_ELV, troughcolor=BG_CARD,
        highlightthickness=0, borderwidth=0)
    tr_sb.pack(side="right", fill="y")
    track_box = tki.Listbox(tr_frame, bg=BG_CARD, fg=TX1, font=F_LIST, relief=tki.FLAT,
        borderwidth=0, selectbackground=ACCENT_BG, selectforeground=ACCENT,
        highlightthickness=0, activestyle="none", yscrollcommand=tr_sb.set)
    track_box.pack(fill="both", expand=True)
    tr_sb.config(command=track_box.yview)

    # ── Events ────────────────────────────────────────────────────
    def on_playlist_select(ev):
        if not spotify_connected or not sp:
            return
        sel = pl_box.curselection()
        if not sel:
            return
        pl = _playlists_data[int(sel[0])]
        try:
            track_box.delete(0, tki.END)
            _tracks_data.clear()
            res = sp.playlist_tracks(pl['id'], limit=50)
            for item in res['items']:
                t = item.get('track')
                if t:
                    art = ", ".join([a['name'] for a in t['artists']])
                    track_box.insert(tki.END, f"  {t['name']}  —  {art}")
                    _tracks_data.append(t)
            tr_count.config(text=f"{len(_tracks_data)}")
        except Exception as e:
            print(f"Load tracks error: {e}")

    def on_track_dblclick(ev):
        sel = track_box.curselection()
        if not sel:
            return
        t = _tracks_data[int(sel[0])]
        art = ", ".join([a['name'] for a in t['artists']])
        add_to_queue_fn(t['name'], art, t)

    pl_box.bind("<<ListboxSelect>>", on_playlist_select)
    track_box.bind("<Double-Button-1>", on_track_dblclick)

    def _load_playlists():
        if not spotify_connected or not sp:
            return
        try:
            pl_box.delete(0, tki.END)
            _playlists_data.clear()
            res = sp.current_user_playlists(limit=50)
            for p in res['items']:
                pl_box.insert(tki.END, f"  {p['name']}  ({p['tracks']['total']})")
                _playlists_data.append(p)
            pl_count.config(text=f"{len(res['items'])}")
        except Exception as e:
            print(f"Load playlists error: {e}")
