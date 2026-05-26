import struct, json, os, shutil, subprocess, tempfile, re, sys
from pathlib import Path
from io import BytesIO
from datetime import datetime
from dataclasses import dataclass, field

if getattr(sys, 'frozen', False):
    _ROOT_DIR = Path(sys.executable).parent
else:
    _ROOT_DIR = Path(__file__).resolve().parent.parent

_TOOLS_DIR = _ROOT_DIR / "tools"
os.environ["PATH"] = str(_TOOLS_DIR) + os.pathsep + os.environ.get("PATH", "")
try:
    os.add_dll_directory(str(_TOOLS_DIR))
except Exception:
    pass


@dataclass
class SongInfo:
    index: int
    title: str = ""
    artist: str = ""
    duration_sec: float = 0
    frequency: int = 48000
    channels: int = 2
    data_size: int = 0
    data_offset: int = 0
    samples_count: int = 0


@dataclass
class BankInfo:
    name: str
    path: Path
    display_name: str = ""
    fev_size: int = 0
    fsb5_size: int = 0
    fsb5_offset: int = 0
    num_songs: int = 0
    songs: list = field(default_factory=list)


RADIO_NAMES = {
    "R1": "Hospital Records",
    "R2": "Horizon Pulse",
    "R3": "Horizon XS",
    "R4": "Horizon Bass Arena",
    "R5": "Horizon Block Party",
    "R6": "Gacha City Radio",
    "R7": "Horizon Symphony",
    "R8": "Horizon Future Beat",
    "R9": "Horizon Neon",
    "R10": "Horizon Rewind",
}


def ensure_banks_dir():
    root = _ROOT_DIR
    cfg = _load_json(root / "config" / "project.json")
    banks_dir = root / cfg.get("song_maps_dir", "config/banks")
    banks_dir.mkdir(parents=True, exist_ok=True)
    return banks_dir, cfg


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def detect_game_dir(project_dir: Path) -> Path:
    for parent in [project_dir.parent, project_dir.parent.parent]:
        candidate = parent / "media" / "Audio" / "FMODBanks"
        if candidate.exists():
            return parent
    return project_dir.parent


def detect_banks():
    project_dir = _ROOT_DIR
    cfg = _load_json(project_dir / "config" / "project.json")
    game_dir = detect_game_dir(project_dir)
    banks_dir = game_dir / "media" / "Audio" / "FMODBanks"
    if not banks_dir.exists():
        return []

    result = []
    for f in sorted(banks_dir.glob("R*_Tracks_*.assets.bank")):
        size = f.stat().st_size
        if size < 1024 * 1024:
            continue
        radio_id = f.stem.split("_")[0]
        name = f.stem.replace(".assets", "")
        display = RADIO_NAMES.get(radio_id, radio_id)
        result.append({
            "name": name,
            "bank_file": f.name,
            "display_name": display,
            "size_mb": round(size / 1024 / 1024, 1),
            "file_size": size,
        })
    return result


class NovaHorizonEngine:
    def __init__(self, project_dir: str = None):
        self.project_dir = Path(project_dir or _ROOT_DIR)
        self.config = _load_json(self.project_dir / "config" / "project.json")
        self.game_dir = detect_game_dir(self.project_dir)
        self.banks_dir = self.game_dir / "media" / "Audio" / "FMODBanks"
        self.radio_info_path = self.game_dir / "media" / "Audio" / "RadioInfo_CN.xml"
        self.backup_dir = self.project_dir / self.config["backup_dir"]
        self.extracted_dir = self.project_dir / self.config["extracted_dir"]
        self.song_maps_dir = self.project_dir / self.config.get("song_maps_dir", "config/banks")
        self.tool_dir = self.project_dir / "tools"

        self.ffmpeg = self.tool_dir / "ffmpeg.exe"
        self.fsbankcl = self.tool_dir / "fsbankcl.exe"

        self._current_bank = None
        self._song_map = []

    @property
    def current_bank(self):
        return self._current_bank

    @current_bank.setter
    def current_bank(self, value):
        self._current_bank = value
        self._song_map = self._load_song_map(value)

    def _song_map_path(self, bank_name: str):
        return self.song_maps_dir / f"song_map_{bank_name}.json"

    def _load_song_map(self, bank_name: str) -> list:
        path = self._song_map_path(bank_name)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_song_map(self, bank_name: str, data: list):
        self.song_maps_dir.mkdir(parents=True, exist_ok=True)
        with open(self._song_map_path(bank_name), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_bank_info(self, bank_name: str) -> BankInfo:
        bank_file = self.banks_dir / f"{bank_name}.assets.bank"
        if not bank_file.exists():
            raise FileNotFoundError(f"Bank 文件不存在: {bank_file}")

        with open(bank_file, "rb") as f:
            data = f.read()
        off = data.find(b"FSB5")
        if off < 0:
            raise ValueError("未找到 FSB5 数据")
        fev = data[:off]
        fsb5 = data[off:]

        h_num = struct.unpack("<I", fsb5[8:12])[0]
        h_shdr = struct.unpack("<I", fsb5[12:16])[0]
        h_name = struct.unpack("<I", fsb5[16:20])[0]
        h_data = struct.unpack("<I", fsb5[20:24])[0]

        buf = BytesIO(fsb5)
        buf.seek(60)
        songs = []
        for i in range(h_num):
            raw = struct.unpack("<Q", buf.read(8))[0]
            next_chunk = raw & 1
            freq_code = (raw >> 1) & 0xF
            channels = ((raw >> 5) & 1) + 1
            d_off = ((raw >> 6) & 0xFFFFFFF) * 16
            sc = (raw >> 34) & 0x3FFFFFFF
            ft = {1:8000,2:11000,3:11025,4:16000,5:22050,6:24000,7:32000,8:44100,9:48000}
            freq = ft.get(freq_code, 48000)
            while next_chunk:
                ch = struct.unpack("<I", buf.read(4))[0]
                next_chunk = ch & 1
                buf.read((ch >> 1) & 0xFFFFFF)
            info = {"index": i, "title": f"Track {i}", "artist": ""}
            if self._song_map and i < len(self._song_map):
                info = self._song_map[i]
            songs.append(SongInfo(
                index=i,
                title=info["title"],
                artist=info.get("artist", ""),
                duration_sec=sc / freq if freq > 0 else 0,
                frequency=freq,
                channels=channels,
                data_size=0,
                data_offset=d_off,
                samples_count=sc,
            ))

        for i in range(h_num - 1):
            songs[i].data_size = songs[i + 1].data_offset - songs[i].data_offset
        if songs:
            songs[-1].data_size = h_data - songs[-1].data_offset

        radio_id = bank_name.split("_")[0]
        bi = BankInfo(
            name=bank_name,
            path=bank_file,
            display_name=RADIO_NAMES.get(radio_id, radio_id),
            fev_size=len(fev),
            fsb5_size=len(fsb5),
            fsb5_offset=off,
            num_songs=h_num,
            songs=songs,
        )
        return bi

    def auto_generate_song_map(self, bank_name: str) -> list:
        bank_file = self.banks_dir / f"{bank_name}.assets.bank"
        radio_id = bank_name.split("_")[0]
        prefix = f"HZ6_{radio_id}_"

        with open(bank_file, "rb") as f:
            data = f.read()
        off = data.find(b"FSB5")
        fsb5 = data[off:]

        h_num = struct.unpack("<I", fsb5[8:12])[0]
        buf = BytesIO(fsb5)
        buf.seek(60)

        samples = []
        for i in range(h_num):
            raw = struct.unpack("<Q", buf.read(8))[0]
            next_chunk = raw & 1
            sc = (raw >> 34) & 0x3FFFFFFF
            while next_chunk:
                ch = struct.unpack("<I", buf.read(4))[0]
                next_chunk = ch & 1
                buf.read((ch >> 1) & 0xFFFFFF)
            samples.append(sc)

        if not self.radio_info_path.exists():
            result = [{"index": i, "title": f"Track {i}", "artist": ""} for i in range(h_num)]
            self._save_song_map(bank_name, result)
            return result

        with open(self.radio_info_path, encoding="utf-8") as f:
            xml = f.read()

        entries = []
        for m in re.finditer(
            rf'<Sample\s+SoundName="{re.escape(prefix)}([^"]+)".*?'
            rf'SampleLength="(\d+)".*?SampleRate="(\d+)".*?'
            rf'DisplayName="([^"]*)" Artist="([^"]*)"',
            xml
        ):
            entries.append({
                "samples": int(m.group(2)),
                "freq": int(m.group(3)),
                "display": m.group(4),
                "artist": m.group(5),
            })

        unmatched = list(entries)
        result = [None] * len(samples)
        used = set()

        def best_match(sc):
            best, best_dist = None, 999999999
            for i, e in enumerate(unmatched):
                if i in used:
                    continue
                d = abs(sc - e["samples"])
                if d < best_dist:
                    best_dist = d
                    best = i
            return best

        for i, sc in enumerate(samples):
            idx = best_match(sc)
            if idx is not None and unmatched[idx]:
                e = unmatched[idx]
                used.add(idx)
                result[i] = {"index": i, "title": e["display"], "artist": e["artist"],
                             "_samples": sc}
            else:
                result[i] = {"index": i, "title": f"Track {i}", "artist": "", "_samples": sc}

        self._save_song_map(bank_name, result)
        return result

    def read_bank(self, bank_name: str = None):
        name = bank_name or self._current_bank
        if not name:
            raise ValueError("没有指定 Bank")
        bank_file = self.banks_dir / f"{name}.assets.bank"
        with open(bank_file, "rb") as f:
            data = f.read()
        offset = data.find(b"FSB5")
        if offset < 0:
            raise ValueError("未找到 FSB5 数据")
        return data, data[:offset], data[offset:], offset

    def verify_mapping(self, bank_name: str = None):
        name = bank_name or self._current_bank
        if not name:
            return True
        sm = self._load_song_map(name)
        if not sm or "_samples" not in (sm[0] if sm else {}):
            return True

        data, _, fsb5, _ = self.read_bank(name)
        h_num = struct.unpack("<I", fsb5[8:12])[0]
        if h_num != len(sm):
            return False

        buf = BytesIO(fsb5)
        buf.seek(60)
        for i in range(h_num):
            raw = struct.unpack("<Q", buf.read(8))[0]
            nc = raw & 1
            sc = (raw >> 34) & 0x3FFFFFFF
            while nc:
                ch = struct.unpack("<I", buf.read(4))[0]
                nc = ch & 1
                buf.read((ch >> 1) & 0xFFFFFF)
            stored = sm[i].get("_samples")
            if stored is not None and stored != sc:
                return False
        return True

    def extract_songs(self, bank_name: str = None, out_dir: str = None) -> list:
        os.environ["PATH"] = str(self.tool_dir.resolve()) + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(str(self.tool_dir.resolve()))
        except Exception:
            pass
        import fsb5

        name = bank_name or self._current_bank
        if not name:
            raise ValueError("没有指定 Bank")

        _, _, fsb5_data, _ = self.read_bank(name)
        fsb = fsb5.FSB5(fsb5_data)

        out = Path(out_dir) if out_dir else (self.extracted_dir / name)
        out.mkdir(parents=True, exist_ok=True)

        sm = self._load_song_map(name)

        result = []
        for i, sample in enumerate(fsb.samples):
            ogg = fsb.rebuild_sample(sample)
            info = sm[i] if i < len(sm) else {"title": f"Track{i}", "artist": ""}
            safe = re.sub(r'[<>:"/\\|?*]', '', f"{i:02d} - {info['title']}.ogg")
            path = out / safe
            with open(path, "wb") as f:
                f.write(ogg)
            result.append({"index": i, "file": safe, "title": info["title"], "artist": info.get("artist", "")})

        mp = out / "song_mapping.json"
        with open(mp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return result

    def encode_song(self, audio_path: str) -> bytes:
        audio_path = Path(audio_path)
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "temp.wav"
            r = subprocess.run([str(self.ffmpeg), "-y", "-i", str(audio_path),
                                "-ar", "48000", "-ac", "2", "-sample_fmt", "s16",
                                str(wav)], capture_output=True)
            if r.returncode != 0:
                raise RuntimeError(f"FFmpeg 转码失败: {r.stderr.decode(errors='ignore')[:200]}")

            fsb_out = Path(tmp) / "out.fsb"
            r2 = subprocess.run([str(self.fsbankcl), "-o", str(fsb_out),
                                 "-format", "vorbis", "-quality", "75",
                                 str(wav)], capture_output=True)
            if not fsb_out.exists():
                raise RuntimeError("fsbankcl 编码失败")

            with open(fsb_out, "rb") as f:
                fsb5_data = f.read()

            h_size = 60 + struct.unpack("<I", fsb5_data[12:16])[0] + struct.unpack("<I", fsb5_data[16:20])[0]
            return fsb5_data[h_size:]

    def rebuild_and_patch(self, new_data: dict, bank_name: str = None,
                          dry_run: bool = True) -> bytes:
        name = bank_name or self._current_bank
        if not name:
            raise ValueError("没有指定 Bank")

        data, fev, fsb5_data, fsb5_offset = self.read_bank(name)

        h_num = struct.unpack("<I", fsb5_data[8:12])[0]
        h_shdr = struct.unpack("<I", fsb5_data[12:16])[0]
        h_name = struct.unpack("<I", fsb5_data[16:20])[0]
        h_data = struct.unpack("<I", fsb5_data[20:24])[0]

        buf = BytesIO(fsb5_data)
        buf.seek(60)
        shdr_starts, shdr_sizes = [], []
        for i in range(h_num):
            start = buf.tell()
            raw = struct.unpack("<Q", buf.read(8))[0]
            nc = raw & 1
            while nc:
                ch = struct.unpack("<I", buf.read(4))[0]
                nc = ch & 1
                buf.read((ch >> 1) & 0xFFFFFF)
            shdr_starts.append(start - 60)
            shdr_sizes.append(buf.tell() - start)

        raw_sheaders = fsb5_data[60:60 + h_shdr]
        data_start = 60 + h_shdr + h_name
        orig_data = fsb5_data[data_start:data_start + h_data]

        orig_sizes = []
        for i in range(h_num):
            s = shdr_starts[i]
            raw8 = struct.unpack("<Q", raw_sheaders[s:s+8])[0]
            doff = ((raw8 >> 6) & 0xFFFFFFF) * 16
            if i < h_num - 1:
                nraw8 = struct.unpack("<Q", raw_sheaders[shdr_starts[i+1]:shdr_starts[i+1]+8])[0]
                ndoff = ((nraw8 >> 6) & 0xFFFFFFF) * 16
                orig_sizes.append(ndoff - doff)
            else:
                orig_sizes.append(h_data - doff)

        new_offsets, cur = [], 0
        for i in range(h_num):
            new_offsets.append(cur)
            cur += len(new_data[i]) if i in new_data else orig_sizes[i]

        new_sheaders = bytearray()
        for i in range(h_num):
            s, sz = shdr_starts[i], shdr_sizes[i]
            raw8 = struct.unpack("<Q", raw_sheaders[s:s+8])[0]
            new_raw = raw8 & ~(0xFFFFFFF << 6)
            new_raw |= ((new_offsets[i] // 16) & 0xFFFFFFF) << 6
            new_sheaders.extend(struct.pack("<Q", new_raw))
            new_sheaders.extend(raw_sheaders[s+8:s+sz])

        out = BytesIO()
        out.write(b"FSB5")
        out.write(struct.pack("<IIIIII", 1, h_num, h_shdr, h_name, cur,
                              struct.unpack("<I", fsb5_data[24:28])[0]))
        out.write(fsb5_data[28:60])
        out.write(bytes(new_sheaders))
        if h_name:
            out.write(fsb5_data[60 + h_shdr:60 + h_shdr + h_name])
        for i in range(h_num):
            if i in new_data:
                out.write(new_data[i])
            else:
                out.write(orig_data[shdr_starts[i]:shdr_starts[i] + orig_sizes[i]])

        new_fsb5 = out.getvalue()
        if dry_run:
            return new_fsb5

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        bak = self.backup_dir / f"{name}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.assets.bank"
        shutil.copy2(self.banks_dir / f"{name}.assets.bank", bak)

        new_bank = bytearray(data)
        new_bank[fsb5_offset:fsb5_offset + len(new_fsb5)] = new_fsb5
        if fsb5_offset + len(new_fsb5) < len(data):
            new_bank = new_bank[:fsb5_offset + len(new_fsb5)]
        (self.banks_dir / f"{name}.assets.bank").write_bytes(new_bank)
        return new_fsb5

    def update_radio_info(self, song_updates: dict, bank_name: str = None):
        name = bank_name or self._current_bank
        if not self.radio_info_path.exists():
            raise FileNotFoundError(f"找不到 {self.radio_info_path}")

        xml = self.radio_info_path.read_text("utf-8")
        bak = self.radio_info_path.with_suffix(f".xml.bak.{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        shutil.copy2(self.radio_info_path, bak)

        radio_id = name.split("_")[0]
        for idx, (title, artist) in song_updates.items():
            pattern = (
                rf'(<SoundName>HZ6_{radio_id}_{idx:02d}</SoundName>.*?)'
                rf'(<DisplayName>)(.*?)(</DisplayName>)(.*?)(<Artist>)(.*?)(</Artist>)'
            )
            replacement = rf'\1\2{title}\4\5\6{artist}\8'
            xml = re.sub(pattern, replacement, xml, count=1, flags=re.DOTALL)

        self.radio_info_path.write_text(xml, "utf-8")
        return {"backup": str(bak)}
