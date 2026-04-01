# PiPlayer v3.0

A modern, high-performance music player built with Python and Tkinter, featuring a unified playback engine for both local files and Spotify integration.

![PiPlayer Interface](https://raw.githubusercontent.com/Zyingx/Basic-Music-Player/main/Logo%20%26%20Stuff/screenshot_placeholder.png)

## ✨ Features

- **Unified Global Queue**: Seamlessly mix local MP3/WAV/FLAC files with Spotify tracks in a single play queue.
- **Spotify Integration**: Full browsing, search, and playlist management (powered by `spotipy`).
- **Dynamic UI**:
    - **Marquee Scrolling**: Auto-scrolling labels for long track titles and artists.
    - **Album Art**: Automatic extraction of embedded art from local files and high-res fetching from Spotify.
    - **Glassmorphism Aesthetics**: Deep dark theme with modern accents and smooth transitions.
- **Smart Playback**:
    - Cross-engine playback coordination.
    - Real-time progress bar with seeking.
    - Shuffle and Repeat modes (Off, All, One).
    - Debounced volume control for responsive Spotify playback.
- **Performance Optimized**: Multi-threaded metadata loading and image processing for a lag-free experience.

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **Spotify Premium** (Required for Spotify playback features)
- **Spotify API Credentials** (Client ID, Secret, and Redirect URI via [Spotify Developer Dashboard](https://developer.spotify.com/dashboard))

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Zyingx/Basic-Music-Player.git
   cd Basic-Music-Player
   ```

2. **Install dependencies**:
   ```bash
   pip install pygame mutagen spotipy Pillow python-dotenv
   ```

3. **Configure Environment**:
   Create a `.env` file in the root directory (or use the one provided) and add your Spotify credentials:
   ```env
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
   ```

4. **Add Local Music**:
   Place your audio files in the `Music/` directory within the project folder.

### Running the App

```bash
python music_player.py
```

## 🛠️ Tech Stack

- **Core**: Python
- **GUI**: Tkinter (with custom modern widgets)
- **Audio Engine**: Pygame (Local), Spotify Web API (Remote)
- **Metadata**: Mutagen
- **Imaging**: Pillow (PIL)
- **Config**: Python-dotenv

## 📜 License

This project is open-source and available under the [MIT License](LICENSE).
