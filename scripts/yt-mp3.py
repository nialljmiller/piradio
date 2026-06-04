import sys
import yt_dlp

def download_youtube_audio(url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': '%(title)s.%(ext)s',
        'ffmpeg_location': '/usr/bin',  # Override broken MESASDK ffmpeg
        'noplaylist': True,  # Only download single video, not 340 songs
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python yt_mp3_ytdlp.py <youtube_url>")
        sys.exit(1)

    url = sys.argv[1].replace("\\", "").strip()
    try:
        download_youtube_audio(url)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
