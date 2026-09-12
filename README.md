# ytfetch 🎥⚡

A feature-rich, beautiful, and 403-resilient YouTube search & downloader CLI tool powered by **yt-dlp** and **Rich**.

---

## Features ✨

- 🎨 **Rich Terminal Interface**: Modern UI with status spinners, formatted search tables, metadata cards, and custom progress bars showing download speed, file size, ETA, and percentage.
- 🛡️ **HTTP 403 Forbidden Resilience**: Built-in player-client fallback rotation (`web`, `tv`, `ios`, `mweb`, `android`) and automatic JS challenge solving to bypass YouTube bot detection.
- 📁 **Smart Default Output**: Downloads automatically default to `~/Videos` (customizable via `-o` / `--output`).
- 🔍 **Interactive Search**: Search YouTube directly and select individual videos or ranges (e.g. `1,3`, `1-4`, `all`) to download interactively.
- ℹ️ **Video Info Inspection**: Preview title, channel, duration, view count, description, and available video/audio formats before downloading.
- 🎵 **Audio Extraction**: Save as MP3, M4A, FLAC, or WAV.
- 📹 **Quality Presets**: Choose resolution presets like `1080p`, `720p`, `480p`, `360p`, or `best`.
- 🍪 **Cookie Integration**: Support for `--cookies-from-browser` (Chrome, Firefox, Brave, Edge, Opera) and export files (`--cookies`).

---

## Installation 🚀

### Using `uv` (Recommended)

```bash
git clone https://github.com/Macowen14/yt_download.git
cd yt_download

# Install dependencies and sync environment
uv sync
```

Once synced, you can run `ytfetch` using `uv`:

```bash
uv run ytfetch --help
```

### System Prerequisites
- **FFmpeg**: Required for audio extraction and format merging.
  - Linux: `sudo apt install ffmpeg`
  - macOS: `brew install ffmpeg`

---

## Usage Guide 📖

### 1. Search YouTube Videos

Search videos and display a formatted result table:

```bash
uv run ytfetch search "python tutorial" -n 5
```

#### Interactive Search & Download (`-i` / `--interactive`)

Search YouTube and pick videos to download immediately:

```bash
uv run ytfetch search "lofi hip hop" -i
```

Prompt:
```text
Select video number(s) to download (e.g. 1,3, 1-3, all, or q to cancel): 1,2
```

### 2. Inspect Video Information (`info` subcommand or `--info` flag)

Inspect video metadata and available format options without downloading:

```bash
uv run ytfetch info "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

or via the `download` subcommand:

```bash
uv run ytfetch download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --info
```

### 3. Download Videos

Download videos to default `~/Videos`:

```bash
uv run ytfetch download "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

#### Download Audio Only (`-a` / `--audio-only`)

Extract high-quality audio (defaults to MP3):

```bash
uv run ytfetch download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -a --audio-format mp3
```

#### Custom Quality (`-q` / `--quality`)

```bash
uv run ytfetch download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -q 1080p
```

#### Custom Output Folder (`-o` / `--output`)

```bash
uv run ytfetch download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" -o ~/Music
```

#### Bypassing Persistent 403 Forbidden Blocks (`--cookies-from-browser`)

If YouTube blocks requests or returns HTTP 403, pass browser cookies:

```bash
uv run ytfetch download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --cookies-from-browser chrome
```

---

## CLI Command Reference 🛠️

| Subcommand | Description | Key Options |
|---|---|---|
| `search` | Search YouTube videos | `-n <num>`, `-i/--interactive`, `-a/--audio-only`, `-q <quality>`, `-o <path>` |
| `download` | Download single/multiple URLs | `-a/--audio-only`, `--audio-format`, `-q <quality>`, `-f <format>`, `--info`, `-o <path>`, `--cookies-from-browser` |
| `info` | Inspect video details & formats | `--cookies`, `--cookies-from-browser` |

---

## License

MIT
