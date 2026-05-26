"""
PyInstaller 打包脚本
生成 NovaHorizonRadio.exe 到 NovaHorizonRadio 根目录

用法:
  python build_exe.py
"""

import os, sys, shutil, subprocess, json
from pathlib import Path


def build():
    root = Path(__file__).parent.resolve()
    venv_python = sys.executable

    print(f"使用 Python: {venv_python}")
    
    pyinstaller_cmd = [venv_python, "-m", "PyInstaller"]
    version = "1.0.1"
    exe_name = f"NovaHorizonRadio_v{version}"

    extra_datas = []
    for src_dir in ["tools", "config", "optional", "core", "gui", "assets"]:
        p = root / src_dir
        if p.exists():
            extra_datas.extend(["--add-data", f"{p}{os.pathsep}{src_dir}"])
    # 确保 banks 子目录也被包含
    banks_dir = root / "config" / "banks"
    banks_dir.mkdir(parents=True, exist_ok=True)

    # 输出到项目根目录
    dist_dir = root
    build_dir = root / "_pybuild"

    cmd = pyinstaller_cmd + [
        "--name", exe_name,
        "--windowed",
        "--onefile",
        "--noconfirm",
        "--clean",
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(build_dir),
    ] + extra_datas + [
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "fsb5",
        "--hidden-import", "requests",
        str(root / "main.py"),
    ]

    print(f"构建 {exe_name}.exe ...")
    print(f"输出位置: {dist_dir / f'{exe_name}.exe'}")
    print(f"耗时: 2-5 分钟\n")

    result = subprocess.run(cmd, cwd=root)
    if result.returncode == 0:
        exe_path = root / f"{exe_name}.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / 1024 / 1024
            print(f"\n打包成功!")
            print(f"  {exe_path} ({size_mb:.1f} MB)")
            print(f"\nEXE 已放在 NovaHorizonRadio 目录下，双击即可运行")

            # 清理临时构建文件
            build_dir = root / "_pybuild"
            if build_dir.exists():
                import shutil
                shutil.rmtree(build_dir)
                print(f"  已清理临时构建文件")
    else:
        print(f"\n打包失败，请检查错误信息")


if __name__ == "__main__":
    build()
