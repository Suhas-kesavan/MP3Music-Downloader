# 🎵 YouTube Music Downloader

A powerful Python application that downloads songs and albums from YouTube with automatic metadata detection and organization. Features smart file naming, album organization, and comprehensive metadata tagging using MusicBrainz integration.

## ✨ Features

- **🎯 Smart Downloads**: Download individual songs or entire playlists/albums
- **🔍 Automatic Metadata Detection**: Extracts artist, title, album, year, and genre information automatically
- **🏷️ MusicBrainz Integration**: Enhanced metadata accuracy through MusicBrainz API
- **📁 Intelligent Organization**: Creates artist/album folder structures automatically  
- **🎧 High Quality Audio**: Downloads in MP3 format at 320kbps
- **📝 Complete ID3 Tagging**: Updates all metadata fields including track numbers
- **🎨 Custom Metadata Override**: Manually specify any metadata field
- **📂 Flexible Output Paths**: Choose where to save your music
- **🔄 Cross-Platform**: Works on Windows, macOS, and Linux

## 🚀 Quick Start

### Installation

1. **Create virtual environment:**
   ```bash
   python -m venv music_downloader_env
   
   # Windows
   music_downloader_env\Scripts\activate
   
   # macOS/Linux  
   source music_downloader_env/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install yt-dlp mutagen requests
   ```

3. **Install FFmpeg:**
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
   - **macOS**: `brew install ffmpeg`
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`

### Basic Usage

**Download a single song:**
```bash
python music_downloader.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

**Download an entire album/playlist:**
```bash
python music_downloader.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --album-mode
```

**Specify custom output directory:**
```bash
python music_downloader.py "URL" --output "/path/to/music/folder"
```

## 📖 Advanced Usage

### Custom Metadata
```bash
python music_downloader.py "URL" \
    --artist "Artist Name" \
    --album "Album Name" \
    --year "2023" \
    --genre "Rock"
```

### Album Download with Metadata
```bash
python music_downloader.py "PLAYLIST_URL" \
    --album-mode \
    --artist "The Beatles" \
    --album "Abbey Road" \
    --year "1969" \
    --genre "Rock"
```

### Disable Auto-Metadata Detection
```bash
python music_downloader.py "URL" --no-auto-metadata
```

## 🎛️ Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output directory path |
| `--album-mode` | `-a` | Download as album (playlist) |
| `--artist` | | Artist name (overrides auto-detection) |
| `--album` | | Album name (overrides auto-detection) |
| `--title` | | Song title (overrides auto-detection) |
| `--year` | | Release year (overrides auto-detection) |
| `--genre` | | Music genre (overrides auto-detection) |
| `--no-auto-metadata` | | Disable automatic metadata detection |

## 📁 File Organization

The application automatically organizes downloads:

**Single Songs:**
```
downloads/
└── Artist Name/
    └── Song Title.mp3
```

**Albums:**
```
downloads/
└── Artist Name/
    └── Album Name/
        ├── 1 - Track One.mp3
        ├── 2 - Track Two.mp3
        └── ...
```

## 🔧 How It Works

1. **URL Processing**: Extracts video/playlist information using yt-dlp
2. **Metadata Extraction**: Parses titles to identify artist and song names
3. **MusicBrainz Lookup**: Searches for additional metadata (album, year, genre)
4. **Audio Download**: Downloads best quality audio available
5. **Format Conversion**: Converts to MP3 at 320kbps using FFmpeg
6. **Metadata Tagging**: Updates ID3 tags with complete information
7. **File Organization**: Moves files to appropriate artist/album folders

## 🎵 Metadata Sources

- **YouTube**: Video titles, upload dates, playlist information
- **MusicBrainz**: Comprehensive music database for accurate metadata
- **User Input**: Manual override for any metadata field
- **Smart Parsing**: Automatic artist/title extraction from video titles

## 🛠️ Requirements

- Python 3.7+
- FFmpeg (system installation)
- Internet connection for downloads and metadata lookup

## 📝 Example Output

```bash
$ python music_downloader.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

Downloading song from: https://www.youtube.com/watch?v=dQw4w9WgXcQ
Created directory: downloads/Rick Astley
[youtube] dQw4w9WgXcQ: Downloading webpage
[download] 100% of 3.28MiB in 00:02
[ExtractAudio] Destination: downloads/Rick Astley/Never Gonna Give You Up.mp3
Updated metadata for: Never Gonna Give You Up.mp3
Downloaded with metadata: {
    'title': 'Never Gonna Give You Up', 
    'artist': 'Rick Astley', 
    'album': 'Whenever You Need Somebody', 
    'year': '1987', 
    'genre': 'Pop'
}
```

## ⚖️ Legal Notice

This tool is for educational purposes and personal use only. Users are responsible for complying with YouTube's Terms of Service and applicable copyright laws. Only download content you have permission to download.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## 📜 License

This project is licensed under the GNU General Public License v3.0 - see the LICENSE file for details.

---

⭐ **Star this repo if you find it helpful!**
