"""
PiPlayer — Spotify Browse Tab
Full Spotify browsing, search, and queue integration.
PREMIUM_ENABLED must be True to allow playback control.
"""

import tkinter as tki
import tkinter.messagebox
import os
import threading
import io

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

PREMIUM_ENABLED = True

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    from spotify_config import (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
                                SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPE,
                                SPOTIFY_BEARER_TOKEN)
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

sp = None
spotify_connected = False
_playlists_data = []
_tracks_data = []


class ModernScrollbar(tki.Canvas):
    """Custom scrollbar widget matching the app's dark theme."""
    def __init__(self, parent, bg="#0a0a0f", fg="#505068", active_fg="#f0f0f5", width=8, borderwidth=0):
        super().__init__(parent, bg=bg, width=width, highlightthickness=0, bd=0)
        self.command = None
        self.fg = fg
        self.active_fg = active_fg
        self.slider = self.create_rectangle(0, 0, width, 0, fill=fg, outline="", width=0)

        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<Button-1>", self.on_click)
        self.bind("<Enter>", lambda e: self.itemconfig(self.slider, fill=self.active_fg))
        self.bind("<Leave>", lambda e: self.itemconfig(self.slider, fill=self.fg))

    def set(self, low, high):
        h = self.winfo_height()
        pad = 2
        y1 = max(pad, float(low) * h)
        y2 = min(h - pad, float(high) * h)
        if y2 - y1 < 10:
            y2 = y1 + 10
        self.coords(self.slider, pad, y1, self.winfo_width() - pad, y2)

    def on_drag(self, event):
        h = self.winfo_height()
        if h == 0: return
        fraction = event.y / h
        if self.command:
            try: self.command("moveto", fraction)
            except Exception: pass

    def on_click(self, event):
        self.on_drag(event)


class EllipsisLabel(tki.Label):
    """A Label that truncates its text with '...' when it overflows."""
    def __init__(self, parent, full_text="", **kwargs):
        super().__init__(parent, **kwargs)
        self._full_text = full_text
        self.config(text=full_text)
        self.bind("<Configure>", self._on_resize)

    def set_text(self, text):
        self._full_text = text
        self._truncate()

    def _on_resize(self, event=None):
        self.after(1, self._truncate)

    def _truncate(self):
        import tkinter.font as tkfont
        try:
            w = self.winfo_width()
            if w <= 1:
                return
            font_info = self.cget("font")
            font = tkfont.Font(font=font_info)
            text = self._full_text
            text_w = font.measure(text)
            if text_w <= w:
                self.config(text=text)
                return
            ellipsis = "..."
            ew = font.measure(ellipsis)
            lo, hi = 0, len(text)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if font.measure(text[:mid]) + ew <= w:
                    lo = mid
                else:
                    hi = mid - 1
            self.config(text=text[:lo] + ellipsis if lo < len(text) else text)
        except Exception:
            pass


def _make_square_thumb(pil_img, size=48):
    if not PIL_AVAILABLE: return pil_img
    return pil_img.resize((size, size), Image.LANCZOS)

def _get_image_from_url(url, size=48):
    if not PIL_AVAILABLE or not url: return None
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            pil_img = Image.open(io.BytesIO(resp.read()))
            return _make_square_thumb(pil_img, size=size)
    except Exception as e:
        print(f"[DEBUG] Img fetch err: {e}")
        return None

def build_spotify_browse(parent, colors, fonts, root_ref, add_to_queue_fn):
    global sp, spotify_connected
    
    # Store references to PhotoImages to prevent garbage collection
    root_ref.C_img_refs = []
    root_ref.T_img_refs = []
    active_track_idx = [-1]
    active_row_widgets = []
    active_pl_idx = [-1]
    active_pl_widgets = []

    if not hasattr(root_ref, 'empty_ph'):
        if PIL_AVAILABLE:
            _img = Image.new('RGBA', (40, 40), (40, 40, 50, 255))
            root_ref.empty_ph = ImageTk.PhotoImage(_img)
        else:
            root_ref.empty_ph = tki.PhotoImage(width=40, height=40)

    # Colors & Fonts
    C = colors
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

    # ── Helpers ─────────────────────────────────────────────
    def card(par, bg=BG_CARD):
        o = tki.Frame(par, bg=BORDER, padx=1, pady=1)
        i = tki.Frame(o, bg=bg)
        i.pack(fill="both", expand=True)
        return o, i

    # ── Connection ─────────────────────────────────────────
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
            # Use manual Bearer token if provided
            if SPOTIFY_BEARER_TOKEN and SPOTIFY_BEARER_TOKEN.strip():
                sp = spotipy.Spotify(auth=SPOTIFY_BEARER_TOKEN.strip())
                print("Using manual Bearer token")
            else:
                # Fall back to OAuth flow
                cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".spotify_cache")
                auth = SpotifyOAuth(
                    client_id=SPOTIFY_CLIENT_ID,
                    client_secret=SPOTIFY_CLIENT_SECRET,
                    redirect_uri=SPOTIFY_REDIRECT_URI,
                    scope=SPOTIFY_SCOPE,
                    cache_path=cache,
                    open_browser=True,
                    show_dialog=True
                )
                sp = spotipy.Spotify(auth_manager=auth)

            user = sp.current_user()
            print("CONNECTED:", user)
            spotify_connected = True
            status_lbl.config(text=f"✓ {user['display_name']}", fg=SP_GREEN)
            conn_btn.config(text="Connected", bg=SP_GREEN, state="disabled")
            _load_playlists()
        except Exception as e:
            tkinter.messagebox.showerror("Error", f"Connection failed:\n{e}")

    conn_btn = tki.Button(conn_body, text=" Connect Spotify",
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

    # ── Main Content Row ───────────────────────────────────
    content_row = tki.PanedWindow(parent, bg=BORDER, orient="horizontal", sashwidth=4, bd=0)
    content_row.pack(fill="both", expand=True)

    # ── Playlists ──────────────────────────────────────────
    pl_o, pl_c = card(content_row)
    content_row.add(pl_o, minsize=150, stretch="always")
    pl_hdr = tki.Frame(pl_c, bg=SP_DARK)
    pl_hdr.pack(fill="x")
    tki.Label(pl_hdr, text="  Playlists", font=F_HDR,
              bg=SP_DARK, fg=SP_GREEN).pack(side="left", pady=6, padx=6)
    pl_count = tki.Label(pl_hdr, text="0", font=F_TINY, bg=SP_DARK, fg=TX3)
    pl_count.pack(side="right", padx=8)

    pl_frame = tki.Frame(pl_c, bg=BG_CARD)
    pl_frame.pack(fill="both", expand=True, padx=4, pady=4)
    pl_canvas = tki.Canvas(pl_frame, bg=BG_CARD, highlightthickness=0, bd=0)
    pl_sb = ModernScrollbar(pl_frame, bg=BG_ELV, fg=TX3, active_fg=TX1)
    pl_sb.command = pl_canvas.yview
    pl_sb.pack(side="right", fill="y")
    pl_canvas.pack(side="left", fill="both", expand=True)
    pl_canvas.configure(yscrollcommand=pl_sb.set)
    pl_inner = tki.Frame(pl_canvas, bg=BG_CARD)
    pl_inner_id = pl_canvas.create_window((0, 0), window=pl_inner, anchor="nw")
    def _pl_canvas_config(e):
        pl_canvas.itemconfig(pl_inner_id, width=e.width)
    pl_canvas.bind("<Configure>", _pl_canvas_config)
    pl_inner.bind("<Configure>", lambda e: pl_canvas.configure(scrollregion=pl_canvas.bbox("all")))

    def _on_pl_mousewheel(event):
        top, bottom = pl_canvas.yview()
        if (event.delta > 0 and top <= 0) or (event.delta < 0 and bottom >= 1):
            return
        pl_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    # ── Tracks ─────────────────────────────────────────────
    tr_o, tr_c = card(content_row)
    content_row.add(tr_o, minsize=150, stretch="always")
    tr_hdr = tki.Frame(tr_c, bg=SP_DARK)
    tr_hdr.pack(fill="x")
    tki.Label(tr_hdr, text="  Tracks", font=F_HDR,
              bg=SP_DARK, fg=SP_GREEN).pack(side="left", pady=6, padx=6)
    tr_count = tki.Label(tr_hdr, text="0", font=F_TINY, bg=SP_DARK, fg=TX3)
    tr_count.pack(side="right", padx=8)

    tr_frame = tki.Frame(tr_c, bg=BG_CARD)
    tr_frame.pack(fill="both", expand=True, padx=4, pady=4)
    tr_canvas = tki.Canvas(tr_frame, bg=BG_CARD, highlightthickness=0, bd=0)
    tr_sb = ModernScrollbar(tr_frame, bg=BG_ELV, fg=TX3, active_fg=TX1)
    tr_sb.command = tr_canvas.yview
    tr_sb.pack(side="right", fill="y")
    tr_canvas.pack(side="left", fill="both", expand=True)
    tr_canvas.configure(yscrollcommand=tr_sb.set)
    tr_inner = tki.Frame(tr_canvas, bg=BG_CARD)
    tr_inner_id = tr_canvas.create_window((0, 0), window=tr_inner, anchor="nw")
    def _tr_canvas_config(e):
        tr_canvas.itemconfig(tr_inner_id, width=e.width)
    tr_canvas.bind("<Configure>", _tr_canvas_config)
    tr_inner.bind("<Configure>", lambda e: tr_canvas.configure(scrollregion=tr_canvas.bbox("all")))

    def _on_tr_mousewheel(event):
        top, bottom = tr_canvas.yview()
        if (event.delta > 0 and top <= 0) or (event.delta < 0 and bottom >= 1):
            return
        tr_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    pl_canvas.bind("<Enter>", lambda e: pl_canvas.bind_all("<MouseWheel>", _on_pl_mousewheel))
    pl_canvas.bind("<Leave>", lambda e: pl_canvas.unbind_all("<MouseWheel>"))
    tr_canvas.bind("<Enter>", lambda e: tr_canvas.bind_all("<MouseWheel>", _on_tr_mousewheel))
    tr_canvas.bind("<Leave>", lambda e: tr_canvas.unbind_all("<MouseWheel>"))

    def add_selected_to_queue(idx=None):
        if idx is None:
            sel = active_track_idx[0]
            if sel < 0 or sel >= len(_tracks_data): return
            t = _tracks_data[sel]
        else:
            if idx < 0 or idx >= len(_tracks_data): return
            t = _tracks_data[idx]
        art = ", ".join([a['name'] for a in t.get('artists', [])])
        add_to_queue_fn(t['name'], art, t)



    # ── Playlist select event ───────────────────────────────
    def on_playlist_select(pidx):
        if not spotify_connected or not sp: return
        if pidx < 0 or pidx >= len(_playlists_data): return
        pl = _playlists_data[pidx]

        for w in tr_inner.winfo_children(): w.destroy()
        _tracks_data.clear()
        tki.Label(tr_inner, text="  ⏳ Loading tracks...", bg=BG_CARD, fg=TX3).pack(pady=10)
        tr_count.config(text="…")
        active_track_idx[0] = -1
        active_row_widgets.clear()

        def _fetch():
            try:
                results = sp.playlist_tracks(pl['id'], limit=100)
                tracks = results.get('items', [])
                while results.get('next') and len(tracks) < 150:
                    results = sp.next(results)
                    tracks.extend(results.get('items', []))

                def _update():
                    for w in tr_inner.winfo_children(): w.destroy()
                    _tracks_data.clear()
                    root_ref.T_img_refs.clear()
                    added = 0
                    for item in tracks:
                        t = item.get('track') or item.get('item')
                        if t is None or not t.get('name'): continue
                        _tracks_data.append(t)
                        idx = added
                        added += 1

                        row = tki.Frame(tr_inner, bg=BG_CARD, cursor="hand2")
                        row.pack(fill="x", pady=2)
                        
                        art_lbl = tki.Label(row, bg=BG_CARD, image=root_ref.empty_ph, bd=0)
                        art_lbl.pack(side="left", padx=(4, 8))

                        # Duration label on the right
                        dur_ms = t.get('duration_ms', 0)
                        dur_s = dur_ms // 1000
                        dur_text = f"{dur_s // 60}:{dur_s % 60:02d}"
                        dur_lbl = tki.Label(row, text=dur_text, font=F_SM, bg=BG_CARD, fg=TX3, anchor="e")
                        dur_lbl.pack(side="right", padx=(4, 10))

                        text_f = tki.Frame(row, bg=BG_CARD)
                        text_f.pack(side="left", fill="both", expand=True)

                        name_lbl = EllipsisLabel(text_f, full_text=t['name'], font=F_LIST, bg=BG_CARD, fg=TX1, anchor="w")
                        name_lbl.pack(fill="x", anchor="w")

                        art = ", ".join([a['name'] for a in t.get('artists', [])])
                        artist_lbl = EllipsisLabel(text_f, full_text=art, font=F_SM, bg=BG_CARD, fg=TX3, anchor="w")
                        artist_lbl.pack(fill="x", anchor="w")

                        widgets = [row, art_lbl, text_f, name_lbl, artist_lbl, dur_lbl]

                        # Double click to add to queue
                        def make_dblclick(i=idx):
                            def dblclk(e):
                                add_selected_to_queue(i)
                            return dblclk

                        dblclk = make_dblclick(idx)
                        for w in widgets:
                            w.bind("<Double-Button-1>", dblclk)

                        # Right-click context menu
                        def make_rclick(i=idx, track=t):
                            def rclk(e):
                                menu = tki.Menu(root_ref, tearoff=0, bg=SP_DARK, fg=TX1, font=F_SM,
                                    activebackground=ACCENT_BG, activeforeground=TX1,
                                    relief=tki.FLAT, bd=1)
                                menu.add_command(label="+ Add to Queue", command=lambda: add_selected_to_queue(i))
                                menu.tk_popup(e.x_root, e.y_root)
                            return rclk

                        rclk = make_rclick(idx, t)
                        for w in widgets:
                            w.bind("<Button-3>", rclk)

                        def make_hover(ws=widgets, i=idx):
                            def eh(_):
                                for x in ws:
                                    if x.winfo_exists() and active_track_idx[0] != i:
                                        x.config(bg=ACCENT_BG)
                            def lh(_):
                                for x in ws:
                                    if x.winfo_exists() and active_track_idx[0] != i:
                                        x.config(bg=BG_CARD)
                            return eh, lh
                        
                        eh, lh = make_hover()
                        for w in widgets:
                            w.bind("<Enter>", eh)
                            w.bind("<Leave>", lh)
                        
                        images = t.get('album', {}).get('images', [])
                        if images:
                            url = images[-1]['url']
                            def load_img(u=url, l=art_lbl):
                                img = _get_image_from_url(u, size=40)
                                if img:
                                    def apply():
                                        if l.winfo_exists():
                                            tk_img = ImageTk.PhotoImage(img)
                                            l.config(image=tk_img, text="")
                                            root_ref.T_img_refs.append(tk_img)
                                    root_ref.after(0, apply)
                            threading.Thread(target=load_img, daemon=True).start()

                    if added == 0:
                        tki.Label(tr_inner, text="  (No playable tracks found)", bg=BG_CARD, fg=TX3).pack(pady=10)
                    tr_count.config(text=f"{len(_tracks_data)}")
                root_ref.after(0, _update)
            except Exception as e:
                root_ref.after(0, lambda: (
                    [w.destroy() for w in tr_inner.winfo_children()],
                    tki.Label(tr_inner, text=f"  ⚠ Error: {str(e)}", bg=BG_CARD, fg=TX3).pack(pady=10),
                    tr_count.config(text="error")
                ))

        threading.Thread(target=_fetch, daemon=True).start()

    # ── Load playlists ──────────────────────────────────────
    def _load_playlists():
        if not spotify_connected or not sp: return
        try:
            res = sp.current_user_playlists(limit=50)
            playlists = res['items']

            def _update():
                for w in pl_inner.winfo_children(): w.destroy()
                _playlists_data.clear()
                root_ref.C_img_refs.clear()
                active_pl_idx[0] = -1
                active_pl_widgets.clear()
                
                pl_click_handlers = []
                
                for idx, p in enumerate(playlists):
                    _playlists_data.append(p)
                    row = tki.Frame(pl_inner, bg=BG_CARD, cursor="hand2")
                    row.pack(fill="x", pady=2)
                    
                    art_lbl = tki.Label(row, bg=BG_CARD, image=root_ref.empty_ph, bd=0)
                    art_lbl.pack(side="left", padx=(4, 8))
                    
                    text_f = tki.Frame(row, bg=BG_CARD)
                    text_f.pack(side="left", fill="both", expand=True)

                    name_lbl = EllipsisLabel(text_f, full_text=f"{p['name']}", font=F_LIST, bg=BG_CARD, fg=TX1, anchor="w")
                    name_lbl.pack(fill="x", anchor="w")

                    cnt = p.get('tracks', {}).get('total') or p.get('items', {}).get('total', 0)
                    count_lbl = EllipsisLabel(text_f, full_text=f"{cnt} tracks", font=F_SM, bg=BG_CARD, fg=TX3, anchor="w")
                    count_lbl.pack(fill="x", anchor="w")

                    widgets = [row, art_lbl, text_f, name_lbl, count_lbl]

                    def make_click(i=idx, ws=widgets):
                        def clk(e):
                            if active_pl_widgets:
                                for w in active_pl_widgets:
                                    if w.winfo_exists(): w.config(bg=BG_CARD)
                            active_pl_idx[0] = i
                            active_pl_widgets.clear()
                            for w in ws:
                                if w.winfo_exists(): w.config(bg=ACCENT_BG)
                                active_pl_widgets.append(w)
                            on_playlist_select(i)
                        return clk

                    clk = make_click(idx, widgets)
                    pl_click_handlers.append(clk)
                    for w in widgets:
                        w.bind("<Button-1>", clk)

                    def make_hover(ws=widgets, i=idx):
                        def eh(_):
                            for x in ws:
                                if x.winfo_exists() and active_pl_idx[0] != i:
                                    x.config(bg=ACCENT_BG)
                        def lh(_):
                            for x in ws:
                                if x.winfo_exists() and active_pl_idx[0] != i:
                                    x.config(bg=BG_CARD)
                        return eh, lh
                    
                    eh, lh = make_hover()
                    for w in widgets:
                        w.bind("<Enter>", eh)
                        w.bind("<Leave>", lh)

                    images = p.get('images', [])
                    if images:
                        # Grab smallest size for playlist but check bounds
                        url = images[-1]['url']
                        def load_img(u=url, l=art_lbl):
                            img = _get_image_from_url(u, size=40)
                            if img:
                                def apply():
                                    if l.winfo_exists():
                                        tk_img = ImageTk.PhotoImage(img)
                                        l.config(image=tk_img, text="")
                                        root_ref.C_img_refs.append(tk_img)
                                root_ref.after(0, apply)
                        threading.Thread(target=load_img, daemon=True).start()

                pl_count.config(text=f"{len(playlists)}")
                if len(_playlists_data) > 0 and pl_click_handlers:
                    pl_click_handlers[0](None)
            root_ref.after(0, _update)
        except Exception as e:
            root_ref.after(0, lambda: (
                [w.destroy() for w in pl_inner.winfo_children()],
                tki.Label(pl_inner, text=f"  ⚠ Error: {e}", bg=BG_CARD, fg=TX3).pack(pady=10),
                pl_count.config(text="error")
            ))