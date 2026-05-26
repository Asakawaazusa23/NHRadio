import subprocess, json, re
from pathlib import Path
from typing import Optional


class NeteaseDownloader:
    def __init__(self, output_dir: str = None, python_path: str = None):
        self.python = python_path or self._find_python()
        self.ncm_cmd = [self.python, "-m", "ncm"]
        self.output_dir = Path(output_dir or "netease_download")

    def _find_python(self) -> str:
        for candidate in [
            r"D:\NovaEcho\venv\Scripts\python.exe",
            r"C:\Users\17359\AppData\Local\Programs\Python\Python313\python.exe",
        ]:
            if Path(candidate).exists():
                return candidate
        return "python"

    def check_installed(self) -> bool:
        try:
            r = subprocess.run(self.ncm_cmd + ["--help"], capture_output=True, timeout=5)
            return r.returncode == 0
        except: return False

    def install(self):
        subprocess.run([self.python, "-m", "pip", "install",
                       "git+https://github.com/codezjx/netease-cloud-music-dl.git"],
                      check=True)

    def get_playlist_info(self, playlist_id: str) -> list:
        import requests
        api_url = f"https://music.163.com/api/playlist/detail?id={playlist_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://music.163.com/",
        }
        r = requests.get(api_url, headers=headers, timeout=15)
        data = r.json()
        if "result" not in data or "tracks" not in data["result"]:
            raise ValueError("无法获取歌单信息，可能歌单不存在或需要登录")
        tracks = data["result"]["tracks"][:25]
        result = []
        for i, t in enumerate(tracks):
            artists = ", ".join(a["name"] for a in t.get("artists", []) or t.get("ar", []))
            result.append({
                "index": i,
                "song_id": t["id"],
                "title": t["name"],
                "artist": artists,
                "duration_ms": t.get("duration", t.get("dt", 0)),
                "album": (t.get("album", {}) or t.get("al", {}) or {}).get("name", ""),
            })
        return result

    def download_playlist(self, playlist_id: str, max_songs: int = 25) -> list:
        info = self.get_playlist_info(playlist_id)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        song_ids = [str(t["song_id"]) for t in info[:max_songs]]
        output_format = "{index}_{title}"
        r = subprocess.run(
            self.ncm_cmd + ["-ss"] + song_ids[:max_songs],
            capture_output=True, text=True, cwd=str(self.output_dir),
            timeout=300
        )
        downloaded = []
        if r.returncode == 0:
            for item in info[:max_songs]:
                mp3_files = list(self.output_dir.glob(f"*{item['title']}*.mp3"))
                if mp3_files:
                    downloaded.append({
                        "index": item["index"],
                        "file": str(mp3_files[0].relative_to(self.output_dir.parent)),
                        "title": item["title"],
                        "artist": item["artist"],
                    })
        return downloaded

    def extract_playlist_id(self, url_or_id: str) -> str:
        m = re.search(r'playlist\?id=(\d+)', url_or_id)
        if m:
            return m.group(1)
        if url_or_id.isdigit():
            return url_or_id
        raise ValueError(f"无法从 '{url_or_id}' 中提取歌单 ID")
