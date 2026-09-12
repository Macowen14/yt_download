#!/usr/bin/env python3
"""
ytfetch — A feature-rich, beautiful, and resilient YouTube search & downloader CLI tool.

Features:
- Built on top of yt-dlp & Rich for a modern CLI experience.
- Automatic 403 Forbidden error recovery via YouTube player-client rotation.
- Browser cookie integration (--cookies-from-browser) & cookie files (--cookies).
- Default download directory set to ~/Videos (customizable via -o / --output).
- Live search status spinners and interactive video selection.
- Comprehensive video info inspection (--info / info subcommand).
- Audio extraction (mp3, flac, wav, m4a) and quality presets (1080p, 720p, 480p, best).
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yt_dlp
except ImportError:
    sys.exit("[!] Missing dependency 'yt-dlp'. Run: uv sync or pip install -U yt-dlp")

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        SpinnerColumn,
        TaskID,
        TextColumn,
        TimeRemainingColumn,
        TransferSpeedColumn,
    )
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("[!] Missing dependency 'rich'. Run: uv sync or pip install -U rich")

console = Console()

# Default download directory set to ~/Videos
DEFAULT_DOWNLOAD_DIR = Path.home() / "Videos"

# Player clients used to recover from YouTube 403 Forbidden bot-detection errors
CLIENT_FALLBACK_ORDER = [None, "android", "ios", "mweb", "tv", "web"]


def _format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds into HH:MM:SS or MM:SS."""
    if not seconds:
        return "N/A"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_filesize(size_bytes: Optional[int]) -> str:
    """Format byte size into human readable string (KB, MB, GB)."""
    if not size_bytes:
        return "Unknown"
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size_bytes} B"


def _format_url(url_or_id: str) -> str:
    """Ensure the target string is a complete URL."""
    if url_or_id.startswith("http://") or url_or_id.startswith("https://"):
        return url_or_id
    # Handle search queries or YouTube IDs
    return f"https://www.youtube.com/watch?v={url_or_id}"


class RichProgressHook:
    """yt-dlp progress hook integrated with Rich Progress bar."""

    def __init__(self, progress: Progress):
        self.progress = progress
        self.task_id: Optional[TaskID] = None
        self.current_filename = ""

    def __call__(self, d: Dict[str, Any]):
        status = d.get("status")
        if status == "downloading":
            filename = Path(d.get("filename", "Downloading...")).name
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)

            if self.task_id is None or filename != self.current_filename:
                self.current_filename = filename
                disp_name = filename if len(filename) <= 35 else filename[:32] + "..."
                self.task_id = self.progress.add_task(f"[cyan]{disp_name}[/cyan]", total=total or 100)

            if total > 0:
                self.progress.update(self.task_id, total=total, completed=downloaded)
            else:
                self.progress.update(self.task_id, completed=downloaded)

        elif status == "finished":
            if self.task_id is not None:
                total = d.get("total_bytes", 100)
                self.progress.update(self.task_id, completed=total)


def search_videos(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Search YouTube using yt-dlp built-in ytsearch and display results in a Rich table."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "remote_components": ["ejs:github"],
    }

    results = []
    search_spec = f"ytsearch{max_results}:{query}"

    with console.status(f"[bold cyan]Searching YouTube for '[bold white]{query}[/bold white]'...[/bold cyan]", spinner="dots"):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(search_spec, download=False)
                entries = info.get("entries", []) if info else []
                for entry in entries:
                    if not entry:
                        continue
                    vid_id = entry.get("id")
                    title = entry.get("title", "Untitled")
                    uploader = entry.get("uploader") or entry.get("channel") or "Unknown"
                    duration = entry.get("duration")
                    url = f"https://www.youtube.com/watch?v={vid_id}"
                    results.append({
                        "id": vid_id,
                        "title": title,
                        "uploader": uploader,
                        "duration": duration,
                        "url": url,
                        "view_count": entry.get("view_count"),
                    })
        except Exception as e:
            console.print(f"[bold red]❌ Search failed:[/bold red] {e}")
            return []

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return []

    # Display Rich Table
    table = Table(title=f"YouTube Search Results for: '{query}'", show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", justify="right", width=4)
    table.add_column("Title", style="bold white")
    table.add_column("Uploader", style="green")
    table.add_column("Duration", style="yellow", justify="center")
    table.add_column("URL", style="dim link blue")

    for idx, r in enumerate(results, 1):
        dur_str = _format_duration(r["duration"])
        table.add_row(str(idx), r["title"], r["uploader"], dur_str, r["url"])

    console.print(table)
    return results


def show_video_info(url_or_id: str, cookies: Optional[str] = None, cookies_from_browser: Optional[str] = None):
    """Inspect and display metadata & format options for a YouTube video in a Rich panel."""
    url = _format_url(url_or_id)
    with console.status("[bold cyan]Fetching video details and available formats...[/bold cyan]", spinner="dots"):
        info = fetch_video_info(url, cookies=cookies, cookies_from_browser=cookies_from_browser)

    if not info:
        console.print("[bold red]No video metadata returned.[/bold red]")
        return

    # Details Panel
    title = info.get("title", "N/A")
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    duration = _format_duration(info.get("duration"))
    views = f"{info.get('view_count', 0):,}" if info.get("view_count") else "N/A"
    upload_date = info.get("upload_date", "N/A")
    if len(upload_date) == 8:
        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
    description = (info.get("description") or "No description provided.").strip()
    if len(description) > 300:
        description = description[:297] + "..."

    details_text = (
        f"[bold cyan]Title:[/bold cyan] [bold white]{title}[/bold white]\n"
        f"[bold cyan]Channel/Uploader:[/bold cyan] [green]{uploader}[/green]\n"
        f"[bold cyan]Duration:[/bold cyan] [yellow]{duration}[/yellow] | "
        f"[bold cyan]Views:[/bold cyan] [magenta]{views}[/magenta] | "
        f"[bold cyan]Uploaded:[/bold cyan] [blue]{upload_date}[/blue]\n"
        f"[bold cyan]Web Page:[/bold cyan] [link={info.get('webpage_url', url)}]{info.get('webpage_url', url)}[/link]\n\n"
        f"[bold white]Description Snippet:[/bold white]\n[dim]{description}[/dim]"
    )

    console.print(Panel(details_text, title="[bold magenta]🎥 Video Details[/bold magenta]", border_style="cyan", padding=(1, 2)))

    # Formats Table
    formats = info.get("formats", [])
    if formats:
        fmt_table = Table(title="Available Formats Summary", show_lines=True, header_style="bold green")
        fmt_table.add_column("Format ID", style="cyan")
        fmt_table.add_column("Ext", style="yellow")
        fmt_table.add_column("Resolution / Type", style="bold white")
        fmt_table.add_column("FPS", style="magenta", justify="right")
        fmt_table.add_column("VCodec", style="dim")
        fmt_table.add_column("ACodec", style="dim")
        fmt_table.add_column("Approx Size", style="blue", justify="right")

        # Filter and present recent relevant formats
        display_formats = [f for f in formats if f.get("vcodec") != "none" or f.get("acodec") != "none"][-12:]
        for f in display_formats:
            fmt_id = str(f.get("format_id", ""))
            ext = str(f.get("ext", ""))
            res = f.get("format_note") or (f"{f.get('width')}x{f.get('height')}" if f.get("height") else "audio only")
            fps = str(f.get("fps") or "-")
            vcodec = str(f.get("vcodec") or "-").split(".")[0]
            acodec = str(f.get("acodec") or "-").split(".")[0]
            size_bytes = f.get("filesize") or f.get("filesize_approx")
            size_str = _format_filesize(size_bytes)
            fmt_table.add_row(fmt_id, ext, res, fps, vcodec, acodec, size_str)

        console.print(fmt_table)


def parse_selection_indices(selection_str: str, max_count: int) -> List[int]:
    """Parse user input selection string like '1,3,5-7' or 'all' into 0-indexed integer list."""
    selection_str = selection_str.strip().lower()
    if selection_str == "all":
        return list(range(max_count))

    selected = set()
    parts = selection_str.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-")
            if len(bounds) == 2 and bounds[0].isdigit() and bounds[1].isdigit():
                start, end = int(bounds[0]), int(bounds[1])
                for idx in range(start, end + 1):
                    if 1 <= idx <= max_count:
                        selected.add(idx - 1)
        elif part.isdigit():
            idx = int(part)
    return sorted(list(selected))


def fetch_video_info(
    url: str,
    cookies: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch video metadata using client fallback order."""
    for client in CLIENT_FALLBACK_ORDER:
        opts: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": [client]}}
        if cookies:
            opts["cookiefile"] = cookies
        if cookies_from_browser:
            opts["cookiesfrombrowser"] = (cookies_from_browser,)

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    return info
        except Exception:
            continue
    return None


def inspect_and_select_format(
    info: Dict[str, Any],
    audio_only: bool = False,
    quality: Optional[str] = None,
    fmt_selector: Optional[str] = None,
    choose_format: bool = False,
) -> str:
    """Inspect video format options and select the best format string."""
    formats = info.get("formats", [])
    title = info.get("title", "Unknown Title")
    duration = _format_duration(info.get("duration"))

    video_fmts = [f for f in formats if f.get("vcodec") != "none"]
    audio_fmts = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]

    res_list = sorted(list(set(f.get("height") for f in video_fmts if f.get("height"))), reverse=True)
    res_str = ", ".join(f"{r}p" for r in res_list) if res_list else "audio only"

    if choose_format and formats:
        fmt_table = Table(title=f"Available Formats for: {title}", show_lines=True, header_style="bold green")
        fmt_table.add_column("Format ID", style="cyan")
        fmt_table.add_column("Ext", style="yellow")
        fmt_table.add_column("Resolution / Type", style="bold white")
        fmt_table.add_column("FPS", style="magenta", justify="right")
        fmt_table.add_column("VCodec", style="dim")
        fmt_table.add_column("ACodec", style="dim")
        fmt_table.add_column("Approx Size", style="blue", justify="right")

        display_formats = [f for f in formats if f.get("vcodec") != "none" or f.get("acodec") != "none"][-20:]
        for f in display_formats:
            fmt_id = str(f.get("format_id", ""))
            ext = str(f.get("ext", ""))
            res = f.get("format_note") or (f"{f.get('width')}x{f.get('height')}" if f.get("height") else "audio only")
            fps = str(f.get("fps") or "-")
            vcodec = str(f.get("vcodec") or "-").split(".")[0]
            acodec = str(f.get("acodec") or "-").split(".")[0]
            size_bytes = f.get("filesize") or f.get("filesize_approx")
            size_str = _format_filesize(size_bytes)
            fmt_table.add_row(fmt_id, ext, res, fps, vcodec, acodec, size_str)

        console.print(fmt_table)
        user_choice = Prompt.ask(
            "[bold cyan]Enter desired format ID[/bold cyan] (e.g. [yellow]137+140[/yellow], [yellow]best[/yellow], or press Enter for default)",
            default="best",
        )
        if user_choice.strip():
            if user_choice.strip().lower() == "best":
                return "bestvideo*+bestaudio[ext=m4a]/bestvideo*+bestaudio/best/b"
            return user_choice.strip()

    if audio_only:
        console.print(f"  [dim]• Duration: {duration} | Mode: Audio Only | Available audio streams: {len(audio_fmts)}[/dim]")
        return "bestaudio/best"

    if fmt_selector:
        console.print(f"  [dim]• Duration: {duration} | Direct format selector: {fmt_selector}[/dim]")
        return fmt_selector

    best_res = f"{res_list[0]}p" if res_list else "best"
    if quality:
        target = quality.lower().replace("p", "")
        if target.isdigit():
            target_val = int(target)
            matched_res = next((r for r in res_list if r <= target_val), res_list[-1] if res_list else None)
            res_desc = f"{matched_res}p (requested {quality})" if matched_res else quality
            console.print(f"  [dim]• Duration: {duration} | Available: {res_str} | Target: {res_desc}[/dim]")
            return f"bestvideo[height<={target_val}]*+bestaudio[ext=m4a]/bestvideo[height<={target_val}]*+bestaudio/bestvideo+bestaudio/best"

    console.print(f"  [dim]• Duration: {duration} | Available resolutions: {res_str} | Selected format: Best ({best_res})[/dim]")
    return "bestvideo*+bestaudio[ext=m4a]/bestvideo*+bestaudio/best/b"


def _build_yt_dlp_opts(
    output_dir: Path,
    audio_only: bool,
    audio_format: str,
    quality: Optional[str],
    fmt_selector: Optional[str],
    client: Optional[str],
    cookies: Optional[str],
    cookies_from_browser: Optional[str],
) -> Dict[str, Any]:
    """Construct options dictionary for yt-dlp."""
    output_dir.mkdir(parents=True, exist_ok=True)

    outtmpl = str(output_dir / "%(title)s.%(ext)s")
    opts: Dict[str, Any] = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "retries": 5,
        "fragment_retries": 5,
        "remote_components": ["ejs:github"],
    }
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": [client]}}

    if cookies:
        opts["cookiefile"] = cookies
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = (cookies_from_browser,)

    if audio_only:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format,
            "preferredquality": "192",
        }]
    else:
        if fmt_selector:
            opts["format"] = fmt_selector
        elif quality:
            q_map = {
                "1080p": "bestvideo[height<=1080]*+bestaudio[ext=m4a]/bestvideo[height<=1080]*+bestaudio/best",
                "720p": "bestvideo[height<=720]*+bestaudio[ext=m4a]/bestvideo[height<=720]*+bestaudio/best",
                "480p": "bestvideo[height<=480]*+bestaudio[ext=m4a]/bestvideo[height<=480]*+bestaudio/best",
                "360p": "bestvideo[height<=360]*+bestaudio[ext=m4a]/bestvideo[height<=360]*+bestaudio/best",
                "best": "bestvideo*+bestaudio[ext=m4a]/bestvideo*+bestaudio/best/b",
            }
            opts["format"] = q_map.get(quality.lower(), "bestvideo*+bestaudio[ext=m4a]/bestvideo*+bestaudio/best/b")
        else:
            opts["format"] = "bestvideo*+bestaudio[ext=m4a]/bestvideo*+bestaudio/best/b"

        opts["merge_output_format"] = "mp4"

    return opts


def download_video(
    url_or_id: str,
    output_dir: Path = DEFAULT_DOWNLOAD_DIR,
    audio_only: bool = False,
    audio_format: str = "mp3",
    quality: Optional[str] = None,
    fmt_selector: Optional[str] = None,
    choose_format: bool = False,
    cookies: Optional[str] = None,
    cookies_from_browser: Optional[str] = None,
) -> bool:
    """Download video/audio with pre-download format inspection and player-client fallback."""
    url = _format_url(url_or_id)
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[bold cyan]⬇️  Preparing download for:[/bold cyan] [underline blue]{url}[/underline blue]")

    # Step 1: Pre-download format and stream type inspection
    with console.status("[bold cyan]Checking available formats and stream types...[/bold cyan]", spinner="dots"):
        info = fetch_video_info(url, cookies=cookies, cookies_from_browser=cookies_from_browser)

    if info:
        video_title = info.get("title", url)
        console.print(f"[bold white]🎥 {video_title}[/bold white]")
        selected_fmt = inspect_and_select_format(
            info=info,
            audio_only=audio_only,
            quality=quality,
            fmt_selector=fmt_selector,
            choose_format=choose_format,
        )
    else:
        console.print("[yellow]⚠️ Could not pre-fetch video metadata. Proceeding with fallback format selection.[/yellow]")
        selected_fmt = fmt_selector or "bestvideo*+bestaudio/best/b"

    console.print(f"[dim]Destination directory: {output_dir}[/dim]")

    # Step 2: Download with client fallback handling
    last_error = None
    for client in CLIENT_FALLBACK_ORDER:
        opts = _build_yt_dlp_opts(
            output_dir=output_dir,
            audio_only=audio_only,
            audio_format=audio_format,
            quality=quality,
            fmt_selector=selected_fmt,
            client=client,
            cookies=cookies,
            cookies_from_browser=cookies_from_browser,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
            transient=True,
        ) as progress:
            opts["progress_hooks"] = [RichProgressHook(progress)]
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                console.print(f"[bold green]✓ Download finished successfully![/bold green] Saved to: [bold underline]{output_dir}[/bold underline]\n")
                return True
            except yt_dlp.utils.DownloadError as e:
                err_str = str(e)
                last_error = err_str
                client_name = client if client else "default"
                if "403" in err_str or "Forbidden" in err_str:
                    console.print(f"[yellow]⚠️ Player client '[bold]{client_name}[/bold]' received 403 Forbidden. Attempting fallback...[/yellow]")
                    continue
                elif "Requested format is not available" in err_str and client is not None:
                    continue
                else:
                    console.print(f"[bold red]❌ Download error:[/bold red] {err_str}\n")
                    return False

    # Display 403 troubleshooting panel if all fallbacks failed
    console.print(
        Panel(
            "[bold red]All YouTube player client fallbacks failed.[/bold red]\n\n"
            "[bold yellow]Troubleshooting Strategies:[/bold yellow]\n"
            " 1. [cyan]Update yt-dlp[/cyan]: YouTube frequently updates signatures. Run:\n"
            "    [bold white]uv pip install -U yt-dlp[/bold white] or [bold white]pip install -U yt-dlp[/bold white]\n\n"
            " 2. [cyan]Pass Browser Cookies[/cyan]: Bypass YouTube bot detection by sending cookies from your browser:\n"
            "    [bold white]ytfetch download <URL> --cookies-from-browser chrome[/bold white] (or firefox/brave/edge)\n\n"
            " 3. [cyan]Use a Cookies File[/cyan]: Export cookies.txt and run:\n"
            "    [bold white]ytfetch download <URL> --cookies /path/to/cookies.txt[/bold white]",
            title="[bold red]Download Failed[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )
    return False


def main():
    parser = argparse.ArgumentParser(
        prog="ytfetch",
        description="A feature-rich, 403-resilient YouTube downloader & search CLI powered by yt-dlp and Rich.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # --- Search Subcommand ---
    p_search = subparsers.add_parser("search", help="Search YouTube videos")
    p_search.add_argument("query", help="Search query string")
    p_search.add_argument("-n", "--num", type=int, default=5, help="Number of search results to return (default: 5)")
    p_search.add_argument("-i", "--interactive", action="store_true", help="Interactive prompt to select videos for download")
    p_search.add_argument("-o", "--output", default=str(DEFAULT_DOWNLOAD_DIR), help=f"Output directory (default: {DEFAULT_DOWNLOAD_DIR})")
    p_search.add_argument("-a", "--audio-only", action="store_true", help="Download audio only")
    p_search.add_argument("--audio-format", default="mp3", choices=["mp3", "m4a", "flac", "wav"], help="Audio codec when --audio-only is used")
    p_search.add_argument("-q", "--quality", choices=["1080p", "720p", "480p", "360p", "best"], help="Video quality preset")
    p_search.add_argument("-F", "--choose-format", action="store_true", help="Interactively choose format from available stream list")
    p_search.add_argument("--cookies", help="Path to cookies.txt file")
    p_search.add_argument("--cookies-from-browser", help="Browser to load cookies from (chrome, firefox, brave, edge, etc.)")

    # --- Download Subcommand ---
    p_download = subparsers.add_parser("download", help="Download YouTube videos by URL or ID")
    p_download.add_argument("urls", nargs="+", help="One or more YouTube URLs or Video IDs")
    p_download.add_argument("-o", "--output", default=str(DEFAULT_DOWNLOAD_DIR), help=f"Output directory (default: {DEFAULT_DOWNLOAD_DIR})")
    p_download.add_argument("-a", "--audio-only", action="store_true", help="Extract audio only")
    p_download.add_argument("--audio-format", default="mp3", choices=["mp3", "m4a", "flac", "wav"], help="Audio codec when --audio-only is used")
    p_download.add_argument("-q", "--quality", choices=["1080p", "720p", "480p", "360p", "best"], help="Video quality preset")
    p_download.add_argument("-f", "--format", help="Direct yt-dlp format selector string")
    p_download.add_argument("-F", "--choose-format", action="store_true", help="Interactively choose format from available stream list")
    p_download.add_argument("--info", action="store_true", help="Display video metadata and formats instead of downloading")
    p_download.add_argument("--cookies", help="Path to cookies.txt file")
    p_download.add_argument("--cookies-from-browser", help="Browser to load cookies from (chrome, firefox, brave, edge, etc.)")

    # --- Info Subcommand ---
    p_info = subparsers.add_parser("info", help="Inspect YouTube video metadata and formats without downloading")
    p_info.add_argument("url", help="YouTube video URL or Video ID")
    p_info.add_argument("--cookies", help="Path to cookies.txt file")
    p_info.add_argument("--cookies-from-browser", help="Browser to load cookies from (chrome, firefox, brave, edge, etc.)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    try:
        if args.command == "search":
            results = search_videos(args.query, max_results=args.num)
            if results and args.interactive:
                choice = Prompt.ask(
                    "\n[bold cyan]Select video number(s) to download[/bold cyan] (e.g. [yellow]1,3[/yellow], [yellow]1-3[/yellow], [yellow]all[/yellow], or [yellow]q[/yellow] to cancel)"
                )
                if choice.strip().lower() not in ("q", "quit", "exit", ""):
                    indices = parse_selection_indices(choice, len(results))
                    if indices:
                        out_path = Path(args.output).expanduser()
                        for idx in indices:
                            item = results[idx]
                            download_video(
                                url_or_id=item["url"],
                                output_dir=out_path,
                                audio_only=args.audio_only,
                                audio_format=args.audio_format,
                                quality=args.quality,
                                choose_format=args.choose_format,
                                cookies=args.cookies,
                                cookies_from_browser=args.cookies_from_browser,
                            )
                    else:
                        console.print("[yellow]No valid videos selected.[/yellow]")

        elif args.command == "download":
            out_path = Path(args.output).expanduser()
            for target_url in args.urls:
                if args.info:
                    show_video_info(target_url, cookies=args.cookies, cookies_from_browser=args.cookies_from_browser)
                else:
                    download_video(
                        url_or_id=target_url,
                        output_dir=out_path,
                        audio_only=args.audio_only,
                        audio_format=args.audio_format,
                        quality=args.quality,
                        fmt_selector=args.format,
                        choose_format=args.choose_format,
                        cookies=args.cookies,
                        cookies_from_browser=args.cookies_from_browser,
                    )

        elif args.command == "info":
            show_video_info(args.url, cookies=args.cookies, cookies_from_browser=args.cookies_from_browser)

    except KeyboardInterrupt:
        console.print("\n[bold red]⚠️ Operation cancelled by user.[/bold red]")
        sys.exit(130)


if __name__ == "__main__":
    main()