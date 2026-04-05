"""PiPlayer v0.0.1 — Music Player with Global Queue"""

import tkinter as tki
from tkinter import filedialog
import tkinter.messagebox
import os, random, time, threading
import pygame
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.id3 import ID3
import spotify_tab
import ctypes
import io

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("[WARN] Pillow not installed. Album art disabled. Run: pip install Pillow")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("[WARN] PyMuPDF not installed. SVG icons disabled. Run: pip install PyMuPDF")

def set_dark_titlebar(window):
    try:
        window.update()
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        set_window_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        get_parent = ctypes.windll.user32.GetParent
        hwnd = get_parent(window.winfo_id())
        rendering_policy = ctypes.c_int(2)
        set_window_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(rendering_policy), ctypes.sizeof(rendering_policy))
    except Exception:
        pass

pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)



BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(BASE_DIR, "Music")
ICON_PATH = os.path.join(BASE_DIR, "Logo & Stuff", "PiPlayer.ico")

# Tell Windows to use the custom icon for the taskbar / apps menu 
# instead of the default Python generic icon.
try:
    if os.name == 'nt':
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(u'company.piplayer.musicplayer.1_0')
except Exception:
    pass

# ── Colors ────────────────────────────────────────────────────────
BG      = "#000000"
BG2     = "#050508"
BG3     = "#0a0a0f"
BG4     = "#111118"
BG5     = "#0d0d14"
GRN     = "#3b82f6"
GRN2    = "#60a5fa"
GRN_BG  = "#0c1a2e"
PRP     = "#7c5cfc"
TX1     = "#f0f0f5"
TX2     = "#9090a8"
TX3     = "#505068"
BRD     = "#1a1a2a"
BRD2    = "#222238"
PGB     = "#12121e"
RED     = "#ff4757"
GRAY    = "#a6a6a6"

# Spotify green accents
SP_GRN    = "#1DB954"
SP_GRN2   = "#1ed760"
SP_GRN_BG = "#0c2e1a"

# YouTube red accents
YT_RED    = "#FF0000"
YT_RED2   = "#ff4444"
YT_RED_BG = "#2e0c0c"

player_icons = {}

def _load_tab_icon(filename, size=18):
    """Load an icon (PNG or SVG) from the Logo & Stuff folder and resize it."""
    if not PIL_AVAILABLE:
        return None
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Logo & Stuff", filename)
        if filename.lower().endswith('.svg'):
            if not PYMUPDF_AVAILABLE:
                print(f"[WARN] Cannot load SVG icon {filename}: PyMuPDF not installed")
                return None
            doc = fitz.open(path)
            pix = doc[0].get_pixmap(alpha=True)
            img = Image.frombytes("RGBA", [pix.width, pix.height], pix.samples)
            img = img.resize((size, size), Image.LANCZOS)
            doc.close()
        else:
            img = Image.open(path).convert('RGBA')
            img = img.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        print(f"[WARN] Could not load icon {filename}: {e}")
        return None

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
        self._vol_timer = None  # debounce timer for Spotify volume

st = State()

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

# ── Scrolling Label (marquee effect for long text) ────────────────

class ScrollSync:
    """Synchronises multiple ScrollingLabels so they scroll together.
    All labels reach their right end before *any* label reverses, and
    vice-versa.  Labels that fit their container simply stay centred."""

    SCROLL_SPEED = 1        # pixels per tick
    TICK_MS      = 30       # ms between ticks
    PAUSE_MS     = 3000     # 3-second pause at each end

    def __init__(self, root_widget):
        self._root = root_widget
        self._labels = []       # list of ScrollingLabel
        self._direction = 1     # 1 → scrolling left, -1 → scrolling right
        self._running = False
        self._after_id = None

    def register(self, label):
        self._labels.append(label)

    # Called whenever any child label changes text / resizes
    def restart(self):
        if self._after_id:
            self._root.after_cancel(self._after_id)
            self._after_id = None
        self._running = False
        self._direction = 1
        for lb in self._labels:
            lb._offset = 0
            lb._place_text()
        # Give layout a moment to settle, then decide if we need to scroll
        self._after_id = self._root.after(500, self._check)

    def _check(self):
        need_scroll = any(lb._needs_scroll() for lb in self._labels)
        if need_scroll:
            self._running = True
            # Initial pause at the left edge
            self._after_id = self._root.after(self.PAUSE_MS, self._tick)
        else:
            self._running = False

    def _tick(self):
        if not self._running:
            return

        # Check if any label still needs to scroll in the current direction
        any_moving = False
        all_at_end = True

        for lb in self._labels:
            max_off = lb._max_offset()
            if max_off <= 0:
                continue  # fits — nothing to do
            # Move one step
            lb._offset += self.SCROLL_SPEED * self._direction
            # Clamp
            if lb._offset >= max_off:
                lb._offset = max_off
            elif lb._offset <= 0:
                lb._offset = 0

            # Has this label reached its end?
            if self._direction == 1 and lb._offset < max_off:
                all_at_end = False
            elif self._direction == -1 and lb._offset > 0:
                all_at_end = False
            any_moving = True
            lb._place_text()

        if not any_moving:
            # Nothing overflows any more (e.g. window resized)
            self._running = False
            for lb in self._labels:
                lb._offset = 0
                lb._place_text()
            return

        if all_at_end:
            # Every scrolling label has reached the end → reverse + pause
            self._direction *= -1
            self._after_id = self._root.after(self.PAUSE_MS, self._tick)
        else:
            self._after_id = self._root.after(self.TICK_MS, self._tick)


class ScrollingLabel:
    """A canvas-based label that auto-scrolls when text overflows.
    Text is centred when it fits; scrolling is driven by a ScrollSync."""

    def __init__(self, parent, text="", font=None, bg="#0e0e1a", fg="#f0f0f5",
                 height=22, sync=None):
        self._font = font or ("Segoe UI", 13, "bold")
        self._fg = fg
        self._bg = bg
        self._text = text
        self._height = height
        self._sync = sync  # optional ScrollSync

        self.canvas = tki.Canvas(parent, bg=bg, highlightthickness=0, bd=0,
                                 height=height)
        self._text_id = self.canvas.create_text(
            0, height // 2, text=text, font=self._font, fill=fg, anchor="w")

        self._offset = 0

        self.canvas.bind("<Configure>", lambda e: self._on_resize())

        if sync:
            sync.register(self)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def grid(self, **kw):
        self.canvas.grid(**kw)

    def config(self, **kw):
        changed = False
        if "text" in kw:
            new_text = kw.pop("text")
            if new_text != self._text:
                self._text = new_text
                self.canvas.itemconfig(self._text_id, text=new_text)
                changed = True
        if "fg" in kw:
            self._fg = kw["fg"]
            self.canvas.itemconfig(self._text_id, fill=self._fg)
        if "font" in kw:
            self._font = kw["font"]
            self.canvas.itemconfig(self._text_id, font=self._font)
            changed = True
        if "bg" in kw:
            self._bg = kw["bg"]
            self.canvas.config(bg=self._bg)
        if changed:
            if self._sync:
                self._sync.restart()
            else:
                self._offset = 0
                self._place_text()

    # ── internal helpers ──────────────────────────────────────────
    def _text_width(self):
        bbox = self.canvas.bbox(self._text_id)
        return (bbox[2] - bbox[0]) if bbox else 0

    def _canvas_width(self):
        return self.canvas.winfo_width()

    def _max_offset(self):
        return max(0, self._text_width() - self._canvas_width())

    def _needs_scroll(self):
        cw = self._canvas_width()
        return cw > 0 and self._text_width() > cw

    def _place_text(self):
        """Position the text item based on current offset.
        Left-align the text when it fits; scroll when overflowing."""
        h = self.canvas.winfo_height() or self._height
        cw = self._canvas_width()
        tw = self._text_width()
        if tw <= cw and cw > 0:
            # Text fits — left-align it
            self.canvas.coords(self._text_id, 0, h // 2)
        else:
            self.canvas.coords(self._text_id, -self._offset, h // 2)

    def _on_resize(self):
        if self._sync:
            self._sync.restart()
        else:
            self._offset = 0
            self._place_text()


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
            # Binary search for max chars that fit
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


# Global scroll synchroniser (created once, wired to root later)
_np_sync = None  # initialised after root is created


class ModernScrollbar(tki.Canvas):
    def __init__(self, parent, bg=BG3, fg=TX3, active_fg=TX1, width=8, borderwidth=0):
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

def fmt_time(s):
    if s <= 0: return "0:00"
    return f"{int(s//60)}:{int(s%60):02d}"

def get_dur(fp):
    # 1. Try mutagen (handles most formats)
    try:
        a = MutagenFile(fp)
        if a and a.info and a.info.length > 0:
            return a.info.length
    except Exception:
        pass
    # 2. Fallback for WAV: read header directly
    if fp.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(fp, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except Exception:
            pass
    # 3. Last resort: pygame.mixer.Sound (loads into memory, but works)
    try:
        snd = pygame.mixer.Sound(fp)
        length = snd.get_length()
        del snd
        if length > 0:
            return length
    except Exception:
        pass
    return 0

def parse_name(fn):
    return os.path.splitext(fn)[0].replace("_", " ")

def scan_music():
    exts = (".mp3", ".wav", ".ogg", ".flac")
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

# ── Album Art Helpers ─────────────────────────────────────────────
ART_SIZE = 58  # thumbnail size in pixels

def _get_local_album_art(filepath):
    """Extract embedded album art from a local audio file. Returns PIL Image or None."""
    if not PIL_AVAILABLE:
        return None
    try:
        audio = MutagenFile(filepath)
        if audio is None:
            return None
        # MP3 (ID3 tags)
        if hasattr(audio, 'tags') and audio.tags:
            for key in audio.tags:
                if key.startswith('APIC') or key == 'APIC:':
                    data = audio.tags[key].data
                    return Image.open(io.BytesIO(data))
        # FLAC
        if hasattr(audio, 'pictures') and audio.pictures:
            return Image.open(io.BytesIO(audio.pictures[0].data))
        # MP4/M4A
        if hasattr(audio, 'tags') and audio.tags:
            for key in ['covr', 'cover']:
                if key in audio.tags:
                    return Image.open(io.BytesIO(bytes(audio.tags[key][0])))
    except Exception as e:
        print(f"[DEBUG] Album art extract error: {e}")
    return None

def _get_spotify_album_art(track_data):
    """Download album art from Spotify track data. Returns PIL Image or None."""
    if not PIL_AVAILABLE:
        return None
    try:
        images = track_data.get('album', {}).get('images', [])
        if not images:
            return None
        # Pick smallest image >= ART_SIZE, or the last one
        url = images[-1]['url']  # smallest
        for img in images:
            if img.get('height', 0) >= ART_SIZE and img.get('height', 0) <= 300:
                url = img['url']
                break
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as resp:
            return Image.open(io.BytesIO(resp.read()))
    except Exception as e:
        print(f"[DEBUG] Spotify album art error: {e}")
    return None

def _make_rounded_thumb(pil_img, size=ART_SIZE, radius=8):
    """Resize and round-corner an image for display."""
    img = pil_img.resize((size, size), Image.LANCZOS)
    # Create rounded mask
    mask = Image.new('L', (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=255)
    # Apply mask
    output = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    img = img.convert('RGBA')
    output.paste(img, (0, 0), mask)
    return output

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
        title, artist = name, "Unknown Artist"
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

def _get_current_source():
    """Return the source of the currently playing track, or None."""
    if st.qi >= 0 and st.qi < len(st.queue):
        return st.queue[st.qi]["source"]
    return None

def _stop_spotify():
    """Pause Spotify playback if active."""
    try:
        if spotify_tab.sp:
            spotify_tab.sp.pause_playback()
    except Exception as e:
        print(f"[DEBUG] Stop Spotify: {e}")

def _stop_local():
    """Stop pygame local playback."""
    try:
        pygame.mixer.music.stop()
    except Exception:
        pass

def play_from_queue(idx):
    """Play item at queue index."""
    if idx < 0 or idx >= len(st.queue): return
    prev_source = _get_current_source()
    st.qi = idx
    item = st.queue[idx]

    # Stop the OTHER engine before switching
    if item["source"] == "local" and prev_source == "spotify":
        _stop_spotify()
    elif item["source"] == "spotify" and prev_source == "local":
        _stop_local()

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
    _update_btn()

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
            # No devices found — try launching Spotify in a background thread
            # to avoid freezing the UI during the wait
            def _launch_and_wait():
                _try_launch_spotify_app()
                # Poll for devices for up to ~10 seconds
                found_devices = None
                for _ in range(5):
                    time.sleep(2)
                    try:
                        result = sp.devices()
                        if result['devices']:
                            found_devices = result
                            break
                    except Exception:
                        pass
                # Back to main thread
                def _after_wait():
                    if found_devices and found_devices['devices']:
                        _start_spotify_playback(item, found_devices)
                    else:
                        tkinter.messagebox.showwarning(
                            "No Device",
                            "Could not find a Spotify device.\n"
                            "Please open the Spotify app and try again."
                        )
                root.after(0, _after_wait)
            threading.Thread(target=_launch_and_wait, daemon=True).start()
            return
        _start_spotify_playback(item, devices)
    except Exception as e:
        tkinter.messagebox.showerror("Playback Error", str(e))

def _start_spotify_playback(item, devices):
    """Start Spotify playback on the first available/active device."""
    try:
        sp = spotify_tab.sp
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
        render_queue()
        update_now_playing_ui()
        _update_btn()
        _start_tick()
    except Exception as e:
        tkinter.messagebox.showerror("Playback Error", str(e))

def _try_launch_spotify_app():
    """Attempt to launch the Spotify desktop app on Windows."""
    import subprocess
    import shutil

    # Try the Windows Spotify URI scheme first (works for both Store and desktop installs)
    try:
        os.startfile("spotify:")
        print("[DEBUG] Launched Spotify via URI scheme")
        return
    except Exception as e:
        print(f"[DEBUG] URI scheme launch failed: {e}")

    # Try common install locations
    spotify_paths = [
        os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps", "Spotify.exe"),
    ]
    for path in spotify_paths:
        if os.path.isfile(path):
            try:
                subprocess.Popen([path], shell=False)
                print(f"[DEBUG] Launched Spotify from: {path}")
                return
            except Exception as e:
                print(f"[DEBUG] Failed to launch {path}: {e}")

    # Fallback: try the system PATH
    spotify_exe = shutil.which("spotify") or shutil.which("Spotify")
    if spotify_exe:
        try:
            subprocess.Popen([spotify_exe], shell=False)
            print(f"[DEBUG] Launched Spotify from PATH: {spotify_exe}")
            return
        except Exception as e:
            print(f"[DEBUG] Failed to launch from PATH: {e}")

    print("[DEBUG] Could not find Spotify app to launch")

def toggle_play():
    if st.qi == -1:
        if st.queue: play_from_queue(0)
        return
    cur_src = _get_current_source()
    if st.paused:
        if cur_src == "local":
            pygame.mixer.music.unpause()
        elif cur_src == "spotify":
            try:
                if spotify_tab.sp: spotify_tab.sp.start_playback()
            except Exception as e:
                print(f"[DEBUG] Resume Spotify: {e}")
        st.paused = False
        st.playing = True
        st._t0 = time.time()
        _start_tick()
    elif st.playing:
        if cur_src == "local":
            pygame.mixer.music.pause()
        elif cur_src == "spotify":
            try:
                if spotify_tab.sp: spotify_tab.sp.pause_playback()
            except Exception as e:
                print(f"[DEBUG] Pause Spotify: {e}")
        st.paused = True
        st.playing = False
        st._off = st.elapsed
    else:
        play_from_queue(st.qi)
    _update_btn()

def stop_playback():
    _stop_local()
    _stop_spotify()
    st.playing = False
    st.paused = False
    st.elapsed = 0
    st._off = 0
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
    syms = ["\uE8EE", "\uE8EE", "\uE8ED"]
    cols = [TX3, GRN, PRP]
    rep_btn.config(text=syms[st.repeat], fg=cols[st.repeat])

def set_vol(v):
    st.volume = float(v) / 100
    pygame.mixer.music.set_volume(st.volume)
    # Debounced Spotify volume (avoid 429 rate limit)
    if _get_current_source() == "spotify" and spotify_tab.sp:
        if st._vol_timer is not None:
            root.after_cancel(st._vol_timer)
        vol_int = int(float(v))
        def _send_vol():
            st._vol_timer = None
            def _sv():
                try:
                    spotify_tab.sp.volume(vol_int)
                except Exception as e:
                    print(f"[DEBUG] Spotify volume: {e}")
            threading.Thread(target=_sv, daemon=True).start()
        st._vol_timer = root.after(500, _send_vol)
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
    cur_src = _get_current_source()
    if cur_src == "local" and st.qi >= 0:
        try:
            pygame.mixer.music.load(st.queue[st.qi]["file"])
            pygame.mixer.music.play(start=pos)
            pygame.mixer.music.set_volume(st.volume)
            st._t0 = time.time(); st._off = pos; st.elapsed = pos
        except Exception: pass
    elif cur_src == "spotify" and spotify_tab.sp:
        pos_ms = int(pos * 1000)
        st._t0 = time.time(); st._off = pos; st.elapsed = pos
        def _sk():
            try:
                spotify_tab.sp.seek_track(pos_ms)
            except Exception as e:
                print(f"[DEBUG] Spotify seek: {e}")
        threading.Thread(target=_sk, daemon=True).start()

# ── Progress tick ─────────────────────────────────────────────────
def _start_tick():
    def tick():
        if st.playing and not st.paused:
            st.elapsed = st._off + (time.time() - st._t0)
            _draw_progress(st.elapsed, st.duration)
            lbl_cur.config(text=fmt_time(st.elapsed))
            lbl_tot.config(text=fmt_time(st.duration))

            cur_src = _get_current_source()
            track_ended = False

            if cur_src == "local":
                # Local: check pygame
                if not pygame.mixer.music.get_busy():
                    track_ended = True
            elif cur_src == "spotify":
                # Spotify: check elapsed vs duration
                if st.duration > 0 and st.elapsed >= st.duration - 0.5:
                    track_ended = True

            if track_ended and st.playing:
                st.playing = False
                play_next()
                return
        if st.playing or st.paused:
            root.after(200, tick)
    tick()

def _update_btn():
    play_btn.config(text="\uE769" if st.playing else "\uE768")

# ═══════════════════════════════════════════════════════════════════
#  UI UPDATE
# ═══════════════════════════════════════════════════════════════════

def update_now_playing_ui():
    if st.qi < 0 or st.qi >= len(st.queue):
        np_title.config(text="No track selected")
        np_artist.config(text="PiPlayer")
        lbl_cur.config(text="0:00"); lbl_tot.config(text="0:00")
        time_row.pack_forget()
        # Reset album art to default icon
        np_art_label.config(image='', text="🎧", font=("Segoe UI", 24), fg=TX3, width=4)
        st._album_art_ref = None
        return
    item = st.queue[st.qi]
    np_title.config(text=item['title'])
    np_artist.config(text=item["artist"])
    lbl_tot.config(text=fmt_time(st.duration))
    time_row.pack(fill="x", pady=(2, 0))

    # Load album art in background
    def _load_art():
        pil_img = None
        if item["source"] == "local":
            pil_img = _get_local_album_art(item.get("file", ""))
        elif item["source"] == "spotify":
            pil_img = _get_spotify_album_art(item.get("track_data", {}))

        def _apply():
            if pil_img and PIL_AVAILABLE:
                thumb = _make_rounded_thumb(pil_img)
                tk_img = ImageTk.PhotoImage(thumb)
                np_art_label.config(image=tk_img, text='', width=ART_SIZE)
                st._album_art_ref = tk_img  # prevent GC
            else:
                # Fallback icon
                icon = "🎵" if item["source"] == "local" else "🎧"
                np_art_label.config(image='', text=icon, font=("Segoe UI", 24), fg=TX3, width=4)
                st._album_art_ref = None
        root.after(0, _apply)

    if PIL_AVAILABLE:
        threading.Thread(target=_load_art, daemon=True).start()
    else:
        icon = "🎵" if item["source"] == "local" else "🎧"
        np_art_label.config(image='', text=icon, font=("Segoe UI", 24), fg=TX3, width=4)

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
    if 'q_frame' not in globals(): return
    for widget in q_frame.winfo_children():
        widget.destroy()
    for i, item in enumerate(st.queue):
        row = tki.Frame(q_frame, bg=BG3)
        row.pack(fill="x", pady=2, padx=2)
        
        if i == st.qi:
            num_lbl = tki.Label(row, text="▶", font=("Segoe UI", 10), fg=GRN, bg=BG3, width=2, anchor="center")
        else:
            num_lbl = tki.Label(row, text=str(i + 1), font=("Segoe UI", 10), fg=TX2, bg=BG3, width=2, anchor="center")
        num_lbl.pack(side="left", padx=(4, 0))
        
        art_lbl = tki.Label(row, bg=BG3, width=4)
        art_lbl.pack(side="left", padx=(2, 8), pady=4)

        x_btn = tki.Label(row, text="✕", font=("Segoe UI", 12), bg=BG3, fg=TX3, cursor="hand2")
        x_btn.pack(side="right", padx=8)
        
        text_f = tki.Frame(row, bg=BG3)
        text_f.pack(side="left", fill="both", expand=True)
        
        fn_to_use = ("Segoe UI", 10, "bold") if i == st.qi else ("Segoe UI", 10)
        col_to_use = GRN if i == st.qi else TX1
        title_lbl = EllipsisLabel(text_f, full_text=item['title'], font=fn_to_use, fg=col_to_use, bg=BG3, anchor="w")
        title_lbl.pack(fill="x", anchor="w")
        
        artist_lbl = EllipsisLabel(text_f, full_text=item['artist'], font=FS, fg=TX3, bg=BG3, anchor="w")
        artist_lbl.pack(fill="x", anchor="w")
        
        # Capture widget references via default args to avoid closure-in-loop bug
        def _make_hover_handlers(row=row, num_lbl=num_lbl, art_lbl=art_lbl,
                                  x_btn=x_btn, text_f=text_f,
                                  title_lbl=title_lbl, artist_lbl=artist_lbl):
            widgets = (row, num_lbl, art_lbl, x_btn, text_f, title_lbl, artist_lbl)
            def _set_hover(state):
                bg_col = BG4 if state else BG3
                for w in widgets:
                    try: w.config(bg=bg_col)
                    except: pass
            def on_enter(e):
                _set_hover(True)
            def on_leave(e):
                _set_hover(False)
            return on_enter, on_leave

        on_enter, on_leave = _make_hover_handlers()
        
        # Bind enter/leave to the row and ALL children
        for w in (row, num_lbl, art_lbl, text_f, title_lbl, artist_lbl, x_btn):
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            
        def _make_x_hover(btn=x_btn):
            def on_x_enter(e):
                try: btn.config(fg=RED)
                except: pass
            def on_x_leave(e):
                try: btn.config(fg=TX3)
                except: pass
            return on_x_enter, on_x_leave

        _x_enter, _x_leave = _make_x_hover()
        x_btn.bind("<Enter>", _x_enter)
        x_btn.bind("<Leave>", _x_leave)
        x_btn.bind("<Button-1>", lambda e, idx=i: remove_from_queue(idx))
        
        def make_player(idx):
            def _play_toggle(e):
                if idx == st.qi:
                    toggle_play()
                else:
                    play_from_queue(idx)
            return _play_toggle
            
        for w in (row, num_lbl, art_lbl, text_f, title_lbl, artist_lbl):
            w.bind("<Double-Button-1>", make_player(i))
            
        icon = "🎵" if item["source"] == "local" else "🎧"
        if 'q_img' in item:
            art_lbl.config(image=item['q_img'], text="", width=40, height=40)
        else:
            art_lbl.config(text=icon, font=("Segoe UI", 16), fg=TX3, width=3, height=1)
            def _load_art(it=item, lbl=art_lbl):
                pil_img = None
                if it["source"] == "local":
                    pil_img = _get_local_album_art(it.get("file", ""))
                elif it["source"] == "spotify":
                    pil_img = _get_spotify_album_art(it.get("track_data", {}))
                
                def _apply():
                    if pil_img and PIL_AVAILABLE:
                        thumb = _make_rounded_thumb(pil_img, size=40)
                        tk_img = ImageTk.PhotoImage(thumb)
                        it['q_img'] = tk_img
                        try: lbl.config(image=tk_img, text="", width=40, height=40)
                        except: pass
                if pil_img: root.after(0, _apply)
            if PIL_AVAILABLE:
                threading.Thread(target=_load_art, daemon=True).start()

def load_local_tracks(rescan=False):
    if rescan or not st.local_files:
        scanned = scan_music()
        # Merge: keep existing files, add any new ones from the Music folder
        existing = set(st.local_files)
        for f in scanned:
            if f not in existing:
                st.local_files.append(f)
                st.local_names.append(parse_name(os.path.basename(f)))
    # If local_names is out of sync (shouldn't happen, but safety check)
    if len(st.local_names) != len(st.local_files):
        st.local_names = [parse_name(os.path.basename(f)) for f in st.local_files]
    # Clear previous rows
    for w in loc_inner.winfo_children():
        w.destroy()
    _local_active_idx[0] = -1
    _local_active_widgets.clear()

    for idx, (fp, name) in enumerate(zip(st.local_files, st.local_names)):
        row = tki.Frame(loc_inner, bg=BG3, cursor="hand2")
        row.pack(fill="x", pady=1)

        # Track name
        name_lbl = EllipsisLabel(row, full_text=f"  {name}", font=FL, bg=BG3, fg=TX1, anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True)

        # Duration on the right
        dur = get_dur(fp)
        dur_text = fmt_time(dur) if dur > 0 else "—"
        dur_lbl = tki.Label(row, text=dur_text, font=FT, bg=BG3, fg=TX3, anchor="e")
        dur_lbl.pack(side="right", padx=(4, 10))

        widgets = [row, name_lbl, dur_lbl]

        # Hover effect
        def make_hover(ws=widgets, i=idx):
            def eh(_):
                for x in ws:
                    if x.winfo_exists() and _local_active_idx[0] != i:
                        x.config(bg=GRN_BG)
            def lh(_):
                for x in ws:
                    if x.winfo_exists() and _local_active_idx[0] != i:
                        x.config(bg=BG3)
            return eh, lh

        eh, lh = make_hover()
        for w in widgets:
            w.bind("<Enter>", eh)
            w.bind("<Leave>", lh)

        # Double click to add to queue
        def make_dblclick(i=idx):
            def dblclk(e):
                add_local_to_queue(i)
            return dblclk

        dblclk = make_dblclick(idx)
        for w in widgets:
            w.bind("<Double-Button-1>", dblclk)

        # Right-click context menu
        def make_rclick(i=idx):
            def rclk(e):
                menu = tki.Menu(root, tearoff=0, bg=BG4, fg=TX1, font=FS,
                    activebackground=GRN_BG, activeforeground=TX1,
                    relief=tki.FLAT, bd=1)
                menu.add_command(label="+ Add to Queue", command=lambda: add_local_to_queue(i))
                menu.add_separator()
                menu.add_command(label="✕ Remove from List", command=lambda: _remove_local_track(i))
                menu.tk_popup(e.x_root, e.y_root)
            return rclk

        rclk = make_rclick(idx)
        for w in widgets:
            w.bind("<Button-3>", rclk)

    local_count.config(text=f"{len(st.local_files)}")

def _remove_local_track(idx):
    """Remove a track from the local list by index."""
    if 0 <= idx < len(st.local_files):
        st.local_files.pop(idx)
        st.local_names.pop(idx)
        load_local_tracks()

# ═══════════════════════════════════════════════════════════════════
#  WINDOW
# ═══════════════════════════════════════════════════════════════════
root = tki.Tk()
set_dark_titlebar(root)
root.title("PiPlayer v0.0.1")
try: root.iconbitmap(ICON_PATH)
except: pass
root.geometry("960x620")
root.minsize(800, 500)
root.configure(bg=BG)
root.option_add("*Font", ("Segoe UI", 10))

# Initialise the scroll synchroniser now that root exists
_np_sync = ScrollSync(root)

# Custom menu bar frame at absolute top
custom_menubar = tki.Frame(root, bg="#212121", height=24)
custom_menubar.pack(side="top", fill="x")

# ── Status bar (pack first = always at bottom) ───────────────────
status = tki.Frame(root, bg=BG4, height=22)
status.pack(side="bottom", fill="x")
status.pack_propagate(False)
tki.Label(status, text="  PiPlayer v0.0.1",
    font=FT, bg=BG4, fg=TX3).pack(side="left", padx=6)
tki.Label(status, text="Ready  ", font=FT, bg=BG4, fg=TX3).pack(side="right", padx=6)

# ═══════════════════════════════════════════════════════════════════
#  BOTTOM PLAYER BAR
# ═══════════════════════════════════════════════════════════════════
btm = tki.Frame(root, bg=BG2, height=100)
btm.pack(side="bottom", fill="x")
btm.pack_propagate(False)

# Progress bar (top of bottom bar)
prog_bar = tki.Canvas(btm, height=6, bg=PGB, highlightthickness=0, bd=0, cursor="hand2")
prog_bar.pack(fill="x", side="top")
prog_bar.bind("<Button-1>", seek)

# Bottom content
btm_inner = tki.Frame(btm, bg=BG2, padx=16)
btm_inner.pack(fill="both", expand=True)

# Left: track info (album art + text)
info_frame = tki.Frame(btm_inner, bg=BG2, width=300)
info_frame.pack(side="left", fill="y", pady=8)
info_frame.pack_propagate(False)

# Album art label
np_art_label = tki.Label(info_frame, bg=BG2, text="", font=("Segoe UI", 24),
    fg=TX3, width=4, anchor="center")
np_art_label.pack(side="left", padx=(0, 12), pady=4)
st._album_art_ref = None  # keep reference to prevent GC

# Text info (right of art)
np_text_frame = tki.Frame(info_frame, bg=BG2)
np_text_frame.pack(side="left", fill="both", expand=True)

np_title = ScrollingLabel(np_text_frame, text="",
    font=FN, bg=BG2, fg=TX1, height=22, sync=_np_sync)
np_title.pack(fill="x", pady=(6, 0))

np_artist = ScrollingLabel(np_text_frame, text="",
    font=FA, bg=BG2, fg=GRN, height=18, sync=_np_sync)
np_artist.pack(fill="x")

# Time labels (below artist)
time_row = tki.Frame(np_text_frame, bg=BG2)
time_row.pack(fill="x", pady=(2, 0))
lbl_cur = tki.Label(time_row, text="0:00", font=FTM, bg=BG2, fg=TX2, anchor="w")

lbl_cur.pack(side="left")
tki.Label(time_row, text=" / ", font=FT, bg=BG2, fg=TX3).pack(side="left")
lbl_tot = tki.Label(time_row, text="0:00", font=FTM, bg=BG2, fg=TX3, anchor="w")
lbl_tot.pack(side="left")
time_row.pack_forget()  # hidden until a track is selected

# Center: controls
ctrl_frame = tki.Frame(btm_inner, bg=BG2)
ctrl_frame.pack(side="left", expand=True, pady=8)

ctrl_row = tki.Frame(ctrl_frame, bg=BG2)
ctrl_row.pack()


class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.widget.bind("<Enter>", self.enter, add="+")
        self.widget.bind("<Leave>", self.leave, add="+")
        self.widget.bind("<Button-1>", self.leave, add="+")

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def showtip(self, event=None):
        text_val = self.text() if callable(self.text) else self.text
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() - 30
        self.tipwindow = tw = tki.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        lbl = tki.Label(tw, text=text_val, justify=tki.LEFT,
                      bg=BG4, fg=TX1, relief=tki.SOLID, borderwidth=1,
                      font=FT)
        lbl.pack(ipadx=5, ipady=2)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class IconButton:
    """A canvas-based icon button with no border."""
    def __init__(self, parent, text="", command=None, size=44, font_size=14,
                 fg=TX1, bg=BG2, hover_fg=GRN2, font_fam="Segoe MDL2 Assets", font_weight="normal", tooltip=None):
        self._fg = fg
        self._hover_fg = hover_fg
        self._command = command
        self.canvas = tki.Canvas(parent, width=size, height=size,
            bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        font_tuple = (font_fam, font_size, font_weight) if font_weight != "normal" else (font_fam, font_size)
        self._text_id = self.canvas.create_text(
            size // 2, size // 2, text=text, font=font_tuple, fill=fg)
        self.canvas.bind("<Enter>", lambda e: self.canvas.itemconfig(self._text_id, fill=self._hover_fg))
        self.canvas.bind("<Leave>", lambda e: self.canvas.itemconfig(self._text_id, fill=self._fg))
        self.canvas.bind("<Button-1>", lambda e: self._command() if self._command else None)
        if tooltip:
            ToolTip(self.canvas, tooltip)

    def pack(self, **kw): self.canvas.pack(**kw)
    def config(self, **kw):
        if "text" in kw: self.canvas.itemconfig(self._text_id, text=kw.pop("text"))
        if "fg" in kw:
            self._fg = kw.pop("fg")
            self.canvas.itemconfig(self._text_id, fill=self._fg)

shuf_btn = IconButton(ctrl_row, "\uE8B1", toggle_shuffle, size=38, font_size=14, fg=TX3, tooltip="Shuffle")
shuf_btn.pack(side="left", padx=8)

prev_btn = IconButton(ctrl_row, "\uE892", play_prev, size=42, font_size=16, tooltip="Previous")
prev_btn.pack(side="left", padx=8)

play_btn = IconButton(ctrl_row, "\uE768", toggle_play, size=52, font_size=20, fg="#ffffff", tooltip=lambda: "Pause" if st.playing else "Play")
play_btn.pack(side="left", padx=8)

next_btn = IconButton(ctrl_row, "\uE893", play_next, size=42, font_size=16, tooltip="Next")
next_btn.pack(side="left", padx=8)

rep_btn = IconButton(ctrl_row, "\uE8EE", toggle_repeat, size=38, font_size=14, fg=TX3, tooltip="Repeat")
rep_btn.pack(side="left", padx=8)

# Right: volume (vertically centered, green seeker)
vol_frame = tki.Frame(btm_inner, bg=BG2, width=210)
vol_frame.pack(side="right", fill="y", pady=12)
vol_frame.pack_propagate(False)

vol_row = tki.Frame(vol_frame, bg=BG2)
vol_row.pack(fill="x", expand=True, anchor="center")

class QueueIcon(tki.Canvas):
    def __init__(self, parent, command=None, size=28, bg=BG2, fg=TX3, hover_fg=GRN2, active_fg=GRN, tooltip=None):
        super().__init__(parent, width=size, height=size, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.size = size
        self.fg = fg
        self.hover_fg = hover_fg
        self.active_fg = active_fg
        self.command = command
        self._is_active = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        if tooltip:
            ToolTip(self, tooltip)
        self._draw(self.fg)

    def set_active(self, active):
        self._is_active = active
        self._draw(self.active_fg if active else self.fg)

    def _on_enter(self, e):
        self._draw(self.active_fg if self._is_active else self.hover_fg)

    def _on_leave(self, e):
        self._draw(self.active_fg if self._is_active else self.fg)

    def _on_click(self, e):
        if self.command:
            self.command()

    def _draw(self, color):
        self.delete("all")
        cx, cy = self.size / 2, self.size / 2
        
        # Dimensions
        w = 14  # Full width of the icon
        hw = w / 2
        line_width = 3 # Thickness of the lines
        
        # 1. Top Pill/Rectangle
        # We use a very thick line with round caps to create a "pill" shape easily
        self.create_line(
            cx - hw, cy - 6, 
            cx + hw, cy - 6, 
            fill=color, width=line_width, capstyle="round"
        )
        
        # 2. Middle Line
        self.create_line(
            cx - hw, cy, 
            cx + hw, cy, 
            fill=color, width=line_width, capstyle="round"
        )
        
        # 3. Bottom Line
        self.create_line(
            cx - hw, cy + 6, 
            cx + hw, cy + 6, 
            fill=color, width=line_width, capstyle="round"
        )

def toggle_queue_panel(e=None):
    if q_panel.winfo_manager():
        q_sash.pack_forget()
        q_panel.pack_forget()
        q_icon.set_active(False)
    else:
        # Repack slightly out of order to ensure exact original layout (q_panel then browse)
        if 'browse' in globals():
            browse.pack_forget()
        q_panel.pack(side="right", fill="y", padx=(0, 10), pady=10)
        q_sash.pack(side="right", fill="y", pady=10)
        if 'browse' in globals():
            browse.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=10)
        q_icon.set_active(True)

q_icon = QueueIcon(vol_row, command=toggle_queue_panel, size=28, bg=BG2, fg=TX3, hover_fg=GRN2, active_fg=GRN, tooltip="Queue")
q_icon.pack(side="left", padx=(0, 10))
q_icon.set_active(True)

v_icon = tki.Label(vol_row, text="🔊", font=("Segoe UI", 12),
    bg=BG2, fg=GRN, cursor="hand2")
v_icon.pack(side="left")
v_icon.bind("<Button-1>", lambda e: toggle_mute())
ToolTip(v_icon, lambda: "Unmute" if st.volume == 0 else "Mute")

class VolumeSeeker:
    def __init__(self, parent, command=None, width=80, height=6, bg=PGB, fg=GRN, active_fg=GRN2):
        self._command = command
        self._val = 0
        self._width = width
        self._height = height
        self._bg = bg
        self._fg = fg
        self._active_fg = active_fg
        
        self.canvas = tki.Canvas(parent, width=width, height=height, bg=bg,
            highlightthickness=0, bd=0, cursor="hand2")
        self.canvas.bind("<Button-1>", self._on_mouse)
        self.canvas.bind("<B1-Motion>", self._on_mouse)
        
    def _on_mouse(self, ev):
        pct = max(0.0, min(1.0, ev.x / self._width))
        self.set(pct * 100, do_callback=True)
        
    def set(self, val, do_callback=False):
        self._val = max(0.0, min(100.0, float(val)))
        self._draw()
        if do_callback and self._command:
            self._command(self._val)
            
    def get(self):
        return self._val
        
    def _draw(self):
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, self._width, self._height, fill=self._bg, outline="")
        fw = (self._val / 100.0) * self._width
        if fw > 0:
            self.canvas.create_rectangle(0, 0, fw, self._height, fill=self._fg, outline="")
            if fw > 4:
                cy = self._height / 2
                self.canvas.create_oval(fw-5, cy-5, fw+5, cy+5, fill=self._active_fg, outline="")
                
    def pack(self, **kw):
        self.canvas.pack(**kw)

vol_sl = VolumeSeeker(vol_row, command=set_vol, width=80, height=6, bg=PGB, fg=GRN, active_fg=GRN2)
vol_sl.set(70)
vol_sl.pack(side="left", padx=(6, 6))

v_pct = tki.Label(vol_row, text="70%", font=FT, bg=BG2, fg=GRN)
v_pct.pack(side="left")

# ═══════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════
hdr = tki.Frame(root, bg=BG2, height=48)
hdr.pack(side="top", fill="x")
hdr.pack_propagate(False)

hdr_in = tki.Frame(hdr, bg=BG2)
hdr_in.pack(fill="x", padx=18)
tki.Label(hdr_in, text="  PiPlayer", font=FLG, bg=BG2, fg=TX1).pack(side="left", pady=8)
tki.Label(hdr_in, text="v0.0.1", font=FT, bg=GRN_BG, fg=GRN, padx=8, pady=2).pack(side="right", pady=12)

tki.Frame(root, bg=BRD, height=1).pack(side="top", fill="x")

# ═══════════════════════════════════════════════════════════════════
#  MAIN CONTENT = Browse Tabs (left) + Queue (right)
# ═══════════════════════════════════════════════════════════════════
main = tki.Frame(root, bg=BG)
main.pack(fill="both", expand=True)

# ── QUEUE PANEL (right) ──────────────────────────────────────────
q_panel = tki.Frame(main, bg=BG, width=280)
q_sash = tki.Frame(main, bg=BG, width=4, cursor="sb_h_double_arrow")
q_panel.pack(side="right", fill="y", padx=(0, 10), pady=10)
q_panel.pack_propagate(False)
q_sash.pack(side="right", fill="y", pady=10)

def resize_q_panel(ev):
    w = q_panel.winfo_width() - ev.x
    w = max(200, min(800, w))
    q_panel.config(width=w)

q_sash.bind("<B1-Motion>", resize_q_panel)
q_sash.bind("<Enter>", lambda e: q_sash.config(bg=TX3))
q_sash.bind("<Leave>", lambda e: q_sash.config(bg=BG))

q_outer, q_card = card(q_panel)
q_outer.pack(fill="both", expand=True)

q_hdr = tki.Frame(q_card, bg=BG4)
q_hdr.pack(fill="x")
tki.Label(q_hdr, text=" Queue", font=FH, bg=BG4, fg=GRN).pack(side="left", pady=8, padx=6)
q_close = tki.Label(q_hdr, text="✕", font=("Segoe UI", 12), bg=BG4, fg=TX3, cursor="hand2")
q_close.pack(side="right", padx=8)
q_close.bind("<Enter>", lambda e: q_close.config(fg=RED))
q_close.bind("<Leave>", lambda e: q_close.config(fg=TX3))
q_close.bind("<Button-1>", toggle_queue_panel)
ToolTip(q_close, "Hide Queue")

# Queue action buttons
q_btn_row = tki.Frame(q_card, bg=BG3, padx=6, pady=4)
q_btn_row.pack(fill="x")

tki.Button(q_btn_row, text="Clear All", command=clear_queue,
    bg=BG4, fg=RED, font=FT, padx=6, pady=1, relief=tki.FLAT,
    cursor="hand2", borderwidth=0, highlightthickness=0).pack(side="right", padx=2)



# Queue scrolled frame
q_lf = tki.Frame(q_card, bg=BG3)
q_lf.pack(fill="both", expand=True, padx=4, pady=4)

q_sb = ModernScrollbar(q_lf, bg=BG3, fg=TX3, active_fg=TX1, width=8)
q_sb.pack(side="right", fill="y", pady=2)

q_canvas = tki.Canvas(q_lf, bg=BG3, highlightthickness=0, bd=0)
q_canvas.pack(side="left", fill="both", expand=True)

q_sb.command = q_canvas.yview
q_canvas.configure(yscrollcommand=q_sb.set)

q_frame = tki.Frame(q_canvas, bg=BG3)
q_canvas_win = q_canvas.create_window((0, 0), window=q_frame, anchor="nw")

def _on_q_frame_configure(e):
    q_canvas.configure(scrollregion=q_canvas.bbox("all"))
q_frame.bind("<Configure>", _on_q_frame_configure)

def _on_q_canvas_configure(e):
    q_canvas.itemconfig(q_canvas_win, width=e.width)
q_canvas.bind("<Configure>", _on_q_canvas_configure)

def _on_q_mousewheel(e):
    if q_panel.winfo_manager():
        top, bottom = q_canvas.yview()
        if (e.delta > 0 and top <= 0) or (e.delta < 0 and bottom >= 1):
            return
        q_canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        
q_canvas.bind("<Enter>", lambda e: root.bind_all("<MouseWheel>", _on_q_mousewheel))
q_canvas.bind("<Leave>", lambda e: root.unbind_all("<MouseWheel>"))

# ── BROWSE PANEL (left) ──────────────────────────────────────────
browse = tki.Frame(main, bg=BG)
browse.pack(side="left", fill="both", expand=True, padx=(10, 8), pady=10)

# Tab bar
tab_bar = tki.Frame(browse, bg=BG)
tab_bar.pack(fill="x", pady=(0, 8))

cur_tab = tki.StringVar(value="local")
local_frame = tki.Frame(browse, bg=BG)
spotify_frame = tki.Frame(browse, bg=BG)
youtube_frame = tki.Frame(browse, bg=BG)

def switch_tab(name):
    cur_tab.set(name)
    # Hide all frames first
    local_frame.pack_forget()
    spotify_frame.pack_forget()
    youtube_frame.pack_forget()
    # Reset all tab buttons
    t_local.config(bg=BG2, fg=TX3)
    t_spot.config(bg=BG2, fg=TX3)
    t_yt.config(bg=BG2, fg=TX3)
    # Show selected
    if name == "local":
        local_frame.pack(fill="both", expand=True)
        t_local.config(bg=GRN_BG, fg=GRN)
    elif name == "spotify":
        spotify_frame.pack(fill="both", expand=True)
        t_spot.config(bg=SP_GRN_BG, fg=SP_GRN)
    elif name == "youtube":
        youtube_frame.pack(fill="both", expand=True)
        t_yt.config(bg=YT_RED_BG, fg=YT_RED)

t_local = tki.Button(tab_bar, text="🎵 Local Music",
    command=lambda: switch_tab("local"),
    bg=GRN_BG, fg=GRN, font=("Segoe UI", 10, "bold"),
    relief=tki.FLAT, cursor="hand2", padx=14, pady=5,
    borderwidth=0, highlightthickness=0)
t_local.pack(side="left", padx=(0, 4))

t_spot = tki.Button(tab_bar, text=" Spotify",
    command=lambda: switch_tab("spotify"),
    bg=BG2, fg=TX3, font=("Segoe UI", 10, "bold"),
    relief=tki.FLAT, cursor="hand2", padx=14, pady=5,
    borderwidth=0, highlightthickness=0)
t_spot.pack(side="left", padx=(0, 4))

t_yt = tki.Button(tab_bar, text=" YouTube",
    command=lambda: switch_tab("youtube"),
    bg=BG2, fg=TX3, font=("Segoe UI", 10, "bold"),
    relief=tki.FLAT, cursor="hand2", padx=14, pady=5,
    borderwidth=0, highlightthickness=0)
t_yt.pack(side="left")

# Apply icons to tab buttons if PIL is available
if PIL_AVAILABLE:
    player_icons['spotify'] = _load_tab_icon('spotify_icon.svg', 18)
    player_icons['youtube'] = _load_tab_icon('youtube_icon.svg', 18)
    if player_icons['spotify']:
        t_spot.config(image=player_icons['spotify'], compound='left')
    if player_icons['youtube']:
        t_yt.config(image=player_icons['youtube'], compound='left')

# Show local tab by default
local_frame.pack(fill="both", expand=True)

# ── LOCAL TAB ─────────────────────────────────────────────────────
loc_outer, loc_card = card(local_frame)
loc_outer.pack(fill="both", expand=True)

loc_hdr = tki.Frame(loc_card, bg=BG4)
loc_hdr.pack(fill="x")
tki.Label(loc_hdr, text="  Tracks", font=FH,
    bg=BG4, fg=GRN).pack(side="left", pady=8, padx=6)
local_count = tki.Label(loc_hdr, text="0", font=FT, bg=BG4, fg=TX3)
local_count.pack(side="right", padx=8)

def add_files():
    files = filedialog.askopenfilenames(title="Add Music Files",
        filetypes=[("Audio", "*.mp3 *.wav *.ogg *.flac"), ("All", "*.*")])
    if not files:
        return
    for f in files:
        if f not in st.local_files:
            st.local_files.append(f)
            st.local_names.append(parse_name(os.path.basename(f)))
    load_local_tracks()  # re-render only, does NOT overwrite st.local_files

add_b = tki.Button(loc_hdr, text="+ Add", command=add_files,
    bg=BG4, fg=TX2, font=FT, padx=6, pady=1, relief=tki.FLAT,
    cursor="hand2", borderwidth=0, highlightthickness=0)
add_b.pack(side="right", padx=4, pady=6)

# Help text
loc_help = tki.Frame(loc_card, bg=BG3, padx=10, pady=4)
loc_help.pack(fill="x")

loc_lf = tki.Frame(loc_card, bg=BG3)
loc_lf.pack(fill="both", expand=True, padx=4, pady=4)

loc_sb = ModernScrollbar(loc_lf, bg=BG3, fg=TX3, active_fg=TX1, width=8)
loc_sb.pack(side="right", fill="y", pady=2)

loc_canvas = tki.Canvas(loc_lf, bg=BG3, highlightthickness=0, bd=0)
loc_canvas.pack(side="left", fill="both", expand=True)
loc_sb.command = loc_canvas.yview
loc_canvas.configure(yscrollcommand=loc_sb.set)

loc_inner = tki.Frame(loc_canvas, bg=BG3)
loc_inner_id = loc_canvas.create_window((0, 0), window=loc_inner, anchor="nw")

def _loc_canvas_config(e):
    loc_canvas.itemconfig(loc_inner_id, width=e.width)
loc_canvas.bind("<Configure>", _loc_canvas_config)
loc_inner.bind("<Configure>", lambda e: loc_canvas.configure(scrollregion=loc_canvas.bbox("all")))

def _on_loc_mousewheel(event):
    top, bottom = loc_canvas.yview()
    if (event.delta > 0 and top <= 0) or (event.delta < 0 and bottom >= 1):
        return
    loc_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
loc_canvas.bind("<Enter>", lambda e: root.bind_all("<MouseWheel>", _on_loc_mousewheel))
loc_canvas.bind("<Leave>", lambda e: root.unbind_all("<MouseWheel>"))

# Active selection state for local tracks
_local_active_idx = [-1]
_local_active_widgets = []

# Keep a dummy local_list reference for backwards compatibility with load_local_tracks
class _LocalListCompat:
    """Thin shim so load_local_tracks() can still call delete/insert."""
    def delete(self, *a): pass
    def insert(self, *a): pass
local_list = _LocalListCompat()

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

# ── YOUTUBE TAB (Coming Soon) ─────────────────────────────────────
yt_outer, yt_card = card(youtube_frame)
yt_outer.pack(fill="both", expand=True)

yt_hdr = tki.Frame(yt_card, bg=BG4)
yt_hdr.pack(fill="x")
tki.Label(yt_hdr, text="  ▶  YouTube", font=FH,
    bg=BG4, fg=YT_RED).pack(side="left", pady=8, padx=6)

yt_body = tki.Frame(yt_card, bg=BG3)
yt_body.pack(fill="both", expand=True)

yt_coming = tki.Label(yt_body, text="Coming Soon",
    font=("Segoe UI", 28, "bold"), bg=BG3, fg=YT_RED)
yt_coming.place(relx=0.5, rely=0.45, anchor="center")



# ═══════════════════════════════════════════════════════════════════
#  MENU BAR (Updated to minimize borders)
# ═══════════════════════════════════════════════════════════════════

# File Button
btn_file = tki.Menubutton(custom_menubar, text=" File ", bg="#212121", fg=TX1,
    activebackground=GRAY, activeforeground=TX1, relief=tki.FLAT, 
    borderwidth=0, cursor="hand2", highlightthickness=0)
btn_file.pack(side="left", padx=4, pady=2)

# Updated fmenu
fmenu = tki.Menu(btn_file, tearoff=0)  
fmenu.add_command(label="Add Files...", command=add_files)
fmenu.add_separator()
fmenu.add_command(label="Exit", command=root.destroy)
btn_file.config(menu=fmenu)

# Help Button
btn_help = tki.Menubutton(custom_menubar, text=" Help ", bg="#212121", fg=TX1,
    activebackground=GRAY, activeforeground=TX1, relief=tki.FLAT, 
    borderwidth=0, cursor="hand2", highlightthickness=0)
btn_help.pack(side="left", padx=4, pady=2)

# Updated hmenu
hmenu = tki.Menu(btn_help, tearoff=0)
hmenu.add_command(label="About", command=lambda: tkinter.messagebox.showinfo(
    "About PiPlayer",
    "PiPlayer v0.0.1\n\nLocal + Spotify Music Player\n"
    "Global queue with mixed playback.\n\nOriginally created in 2020."))
btn_help.config(menu=hmenu)

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
    _stop_spotify()
    pygame.mixer.music.stop()
    pygame.mixer.quit()

    root.destroy()
root.protocol("WM_DELETE_WINDOW", on_close)

root.mainloop()
