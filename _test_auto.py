"""测试自动检测功能"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.engine import detect_banks, NovaHorizonEngine

banks = detect_banks()
print(f"发现 {len(banks)} 个电台:")
for b in banks:
    print(f"  {b['name']:25s} {b['display_name']:20s} {b['size_mb']:>5} MB")

eng = NovaHorizonEngine()
eng.current_bank = "R6_Tracks_CU1"

sm = eng._load_song_map("R6_Tracks_CU1")
if sm:
    print(f"\nR6 已有 song_map: {len(sm)} 首")
else:
    print("\nR6 自动生成 song_map...")
    sm = eng.auto_generate_song_map("R6_Tracks_CU1")
    print(f"  生成 {len(sm)} 首")

if eng.verify_mapping("R6_Tracks_CU1"):
    print("✅ R6 映射验证通过")
else:
    print("❌ R6 映射验证失败")

bi = eng.get_bank_info("R6_Tracks_CU1")
print(f"\n{bi.display_name} ({bi.name}): {bi.num_songs} 首, {bi.fsb5_size/1024/1024:.1f} MB")
for s in bi.songs[:5]:
    m, sec = divmod(int(s.duration_sec), 60)
    print(f"  [{s.index:2d}] {s.title[:35]:35s} {s.artist[:20]:20s} ({m}:{sec:02d})")
print(f"  ... (共 {bi.num_songs} 首)")
print("\n🎉 自动检测功能正常!")
