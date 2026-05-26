#!/usr/bin/env python3
"""NovaHorizonRadio v1.0 极限竞速地平线6 电台音乐替换工具"""

import sys, os
from pathlib import Path
_PROJECT_ROOT = str(Path(__file__).parent.resolve())
os.environ["PROJECT_ROOT"] = _PROJECT_ROOT
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

try:
    from gui.main_window import launch_gui
    launch_gui()
except ImportError as e:
    print(f"GUI 加载失败 ({e})，使用命令行模式")
    from core.engine import NovaHorizonEngine, detect_banks
    eng = NovaHorizonEngine()

    if len(sys.argv) < 2:
        print("用法: python main.py [list|extract|replace|netease] [bank_name]\n")
        banks = detect_banks()
        print(f"可用电台 ({len(banks)}):")
        for b in banks:
            print(f"  {b['name']:25s} {b['display_name']} ({b['size_mb']} MB)")
        print("\n例: python main.py list R6_Tracks_CU1")
        sys.exit(0)

    cmd = sys.argv[1]
    bank_name = sys.argv[2] if len(sys.argv) > 2 else "R6_Tracks_CU1"
    eng.current_bank = bank_name

    print(f"🔄 从XML重建 {bank_name} 歌单映射...")
    sm = eng.auto_generate_song_map(bank_name)
    print(f"✅ 已加载 {len(sm)} 首歌曲映射")

    if cmd == "list":
        bi = eng.get_bank_info(bank_name)
        print(f"\n=== {bi.display_name} ({bi.name}) ===")
        print(f"文件: {bi.path.name} ({bi.fsb5_size/1024/1024:.1f} MB, {bi.num_songs} 首)\n")
        for s in bi.songs:
            m, sec = divmod(int(s.duration_sec), 60)
            print(f"  [{s.index:2d}] {s.title} - {s.artist}  ({m}:{sec:02d})")

    elif cmd == "extract":
        result = eng.extract_songs(bank_name)
        print(f"提取 {len(result)} 首歌曲完成")

    elif cmd == "replace":
        mp3_dir = sys.argv[3] if len(sys.argv) > 3 else input("MP3 文件夹: ")
        dry_run = "--apply" not in sys.argv
        mp3_path = Path(mp3_dir)
        replace_map = {}
        for f in sorted(mp3_path.iterdir()):
            if f.suffix.lower() in ('.mp3', '.ogg', '.wav', '.flac', '.m4a'):
                try:
                    idx = int(f.stem.split("_")[0].split()[0])
                    bi = eng.get_bank_info(bank_name)
                    if 0 <= idx < bi.num_songs:
                        replace_map[idx] = f
                except ValueError:
                    pass
        if not replace_map:
            print("未找到编号命名的音频文件"); sys.exit(1)
        new_data = {}
        for idx, f in sorted(replace_map.items()):
            print(f"  [{idx:2d}] 编码 {f.name} ...", end=" ", flush=True)
            try:
                raw, sc, full_fsb5 = eng.encode_song(f); new_data[idx] = (raw, sc, full_fsb5)
                print(f"✅")
            except Exception as e: print(f"❌ {e}")
        if new_data:
            eng.rebuild_and_patch(new_data, bank_name, dry_run=dry_run)
            print(f"{'试运行' if dry_run else '写入'}完成")

    elif cmd == "netease":
        print("请在 GUI 中使用网易云功能")

    else:
        print(f"未知命令: {cmd}")
        print("可用: list, extract, replace")
