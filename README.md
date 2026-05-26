# NovaHorizonRadio v1.0.1

**Forza Horizon 6 电台音乐替换工具**

将 NovaHorizonRadio 文件夹放入任意电脑的 `ForzaHorizon6` 游戏目录下，双击 EXE 即可自动检测所有电台、解析歌曲列表、替换音频文件。

> **⚠️ 测试状态：** 目前仅验证 **R2 (Horizon Pulse)** 电台替换成功并正常播放，其他电台（R1/R3-R10）尚待测试验证。

---

## 目录

- [项目架构](#项目架构)
- [文件用途说明](#文件用途说明)
- [使用到的第三方项目](#使用到的第三方项目)
- [使用说明书](#使用说明书)
  - [快速开始](#快速开始)
  - [详细操作流程](#详细操作流程)
  - [提取原曲](#提取原曲)
  - [歌曲映射自检机制](#歌曲映射自检机制)
  - [注意事项](#注意事项)

---

## 项目架构

```
NovaHorizonRadio/
│
├── main.py                      # 程序入口，启动 GUI 界面
├── build_exe.py                 # PyInstaller 打包脚本
├── .gitignore                   # Git 忽略规则
│
├── config/
│   ├── project.json             # 项目配置（无绝对路径，全相对路径）
│   └── song_map.json            # 旧版 R6 映射（保留兼容）
│   └── banks/                   # (自动生成) 各电台的 song_map 缓存
│
├── core/
│   ├── __init__.py
│   ├── engine.py                # 核心引擎：Bank 解析、FSB5 重建、编码替换
│   └── netease_dl.py            # 网易云音乐歌单下载集成
│
├── gui/
│   ├── __init__.py
│   └── main_window.py           # PySide6 GUI 界面
│
├── assets/
│   └── icon.png                 # 程序窗口图标
│
├── tools/                       # 第三方命令行工具
│   ├── ffmpeg.exe               # 音频转码 (MP3/FLAC → WAV)
│   ├── fsbankcl.exe             # FMOD Bank 编码器 (WAV → FSB5 Ogg Vorbis)
│   ├── fsbext.exe               # FSB 文件提取器
│   ├── fmod.dll                 # FMOD 运行时库
│   ├── libfsbvorbis.dll         # FSB Vorbis 编解码库
│   ├── libogg.dll / libvorbis.dll
│   └── ...
│
├── backup/                      # (自动生成) Bank 文件备份
├── extracted/                   # (自动生成) 提取的音频文件
└── __pycache__/                 # (自动生成) Python 字节码缓存
```

---

## 文件用途说明

### 核心代码

| 文件 | 用途 |
|---|---|
| `main.py` | 程序入口。优先尝试加载 GUI，失败则提供 CLI 命令行模式 |
| `core/engine.py` | **核心引擎**。负责自动检测游戏目录、扫描 12 个电台、解析 FSB5 Bank 文件、编码替换、song_map 管理、RadioInfo.xml 更新 |
| `core/netease_dl.py` | （没做）网易云音乐集成。通过 NCM API 获取歌单信息并下载歌曲 |
| `gui/main_window.py` | PySide6 GUI。包含电台选择、歌曲列表、音频文件匹配、替换执行、彩色日志等完整界面 |

### 配置

| 文件 | 用途 |
|---|---|
| `config/project.json` | 项目配置。定义工具路径、备份/提取目录、song_map 存储位置。**不含任何绝对路径** |
| `config/banks/song_map_{BankName}.json` | (自动生成) 每个电台的歌曲映射文件，包含歌名、歌手、FSB5 sample 指纹 |

### 工具

| 文件 | 用途 | 版本 |
|---|---|---|
| `tools/ffmpeg.exe` | 音频转码。将 MP3/FLAC/OGG/WAV/M4A 转为 48000Hz/16bit/stereo WAV | FFmpeg 8.0 |
| `tools/fsbankcl.exe` | FMOD 官方 Bank 编码器。将 WAV 编码为 FSB5 Ogg Vorbis (quality 75) | FMOD Studio 1.08.15 |
| `tools/fsbext.exe` | FSB 文件提取器。可提取 FSB4/FSB5 中的音频 | 0.3.8a |
| `tools/fmod.dll` | FMOD 运行时动态链接库 | 1.08.15 |

---

## 使用到的第三方项目

### 命令行工具（已集成在 tools/ 目录）

| 工具 | 来源 | 用途 |
|---|---|---|
| **FFmpeg** 8.0 | [gyan.dev FFmpeg Builds](https://www.gyan.dev/ffmpeg/builds/) | 音频格式转码 |
| **FMOD fsbankcl** 1.08.15 | [FMOD Studio API](https://www.fmod.com/) | 官方 Bank 编码，WAV -> FSB5 Ogg Vorbis |
| **fsbext** 0.3.8a | Luigi Auriemma | FSB 容器提取 |

### 音频格式说明

- **FSB5** (FMOD Sample Bank 5)：FMOD 音频容器格式，内部包含 Ogg Vorbis 编码的音频数据
- **.assets.bank**：Forza Horizon 6 使用的 Bank 文件，结构为 RIFF/FEV 头 + 内嵌 FSB5 数据
- 编码参数：48000Hz / 2ch / 16bit / Vorbis quality 75

---

## 使用说明书

### 快速开始

> 不需要安装 Python。仓库已包含打包好的 `NovaHorizonRadio_v1.0.1.exe`，下载整个仓库解压即可使用。

```
1. 将 NovaHorizonRadio 文件夹放到 ForzaHorizon6 游戏目录下

   ForzaHorizon6/
   ├── Media/
   │   └── Audio/
   │       ├── FMODBanks/          ← 游戏 Bank 文件
   │       └── RadioInfo_CN.xml    ← 电台歌曲信息
   └── NovaHorizonRadio/
       └── NovaHorizonRadio_v1.0.1.exe   ← 双击运行
   
2. 双击 NovaHorizonRadio_v1.0.1.exe
3. 程序自动检测 12 个电台，选择要替换的电台
4. 浏览选择包含 MP3/FLAC/OGG/WAV/M4A 的文件夹
5. 勾选下方要使用的音频文件
6. 点击「按顺序自动匹配」
7. 确认替换状态列显示「待替换」后
8. 点击「执行替换」
```

### 详细操作流程

#### 1. 启动程序

双击 EXE，程序会自动：
- 检测 `../media/Audio/FMODBanks/` 目录是否存在
- 扫描所有 `R*_Tracks_*.assets.bank` 文件
- 解析 `RadioInfo_CN.xml` 获取歌曲信息
- 在左侧日志区显示扫描结果

#### 2. 选择电台

顶部工具栏的「电台」下拉菜单会显示所有检测到的电台，格式为：
```
Hospital Records (R1_Tracks_CU1)  [363.3 MB]
Horizon Pulse (R2_Tracks_CU1)     [288.5 MB]
Gacha City Radio (R6_Tracks_CU1)  [309.1 MB]
...
```

首次选择某个电台时，程序会自动生成 `song_map` 映射文件，确保 FSB5 内部的音频位置与 RadioInfo.xml 的歌曲信息一一对应。

#### 3. 加载音频文件

有两种方式加载用于替换的音频文件：

- **浏览文件夹**：点击「浏览」按钮，选择包含 `.mp3/.ogg/.wav/.flac/.m4a` 文件的文件夹
- **网易云歌单**：粘贴网易云歌单链接或 ID，点击「网易云」按钮自动下载

文件加载后会显示在右下方的「已加载的音频文件」列表中，每个文件前有复选框。

#### 4. 匹配歌曲

**推荐：自动匹配**
1. 在下方列表中勾选要使用的音频文件（或点「全选」）
2. 点击「按顺序自动匹配」按钮
3. 程序会将勾选的文件依次分配到上方电台歌曲的空位中

**手动分配**：双击下方某个文件，自动分配到下一个空位

#### 5. 执行替换

1. 确认替换状态列显示「待替换」
2. 默认勾选「试运行 (仅预览)」可以先测试编码过程是否顺利
3. 点击「执行替换」

**试运行模式**（默认勾选）：
- 只进行音频编码和 FSB5 重建（在内存中）
- 不写入游戏文件，不创建备份
- 用于验证编码过程是否出错

**正式替换**（取消勾选「试运行」）：
- 自动备份原 Bank 文件到 `backup/` 目录
- 将新的 FSB5 数据写入 Bank 文件
- 自动更新 `RadioInfo_CN.xml` 中的歌名和歌手信息
- 替换成功后更新 `song_map.json`，切换电台后仍显示新信息

### 提取原曲

可点击「提取原曲」按钮将当前电台的所有歌曲提取为 OGG 文件，保存在 `extracted/{BankName}/` 目录下。

### 歌曲映射自检机制

每次切换电台时，程序会自动执行 `verify_mapping()` 自检：
- 读取 FSB5 中每个音频的 `samples` 字段（采样数）
- 与 `song_map.json` 中存储的 `_samples` 指纹对比
- 如果发现不匹配（例如 Bank 文件被修改导致偏移），自动重新生成映射

这是防止"播放 A 歌曲结果实际放的是 B 歌曲"的关键机制。

### 注意事项

1. **文件编号**：音频文件不需要编号。音乐文件夹里的 `歌曲名 - 歌手.mp3` 格式才能正常识别
2. **编码耗时**：编码一首歌约需 15-30 秒（取决于 CPU 性能），25 首歌大约需要 10-15 分钟
3. **备份恢复**：替换前会自动备份原 Bank 文件到 `backup/` 目录，文件名格式为 `{BankName}.{时间戳}.assets.bank`
4. **Bank 变体**：每个电台有多个变体（`CU1`、`CU2`、`Disk`、`PDLC1`、`PDLC2`），需要分别替换
5. **游戏版本**：本工具专为 Forza Horizon 6 设计，不兼容前代作品

---

## 进阶：自行打包 Python 源码

> **普通用户不需要这一步。** 仓库的 `NovaHorizonRadio_v1.0.1.exe` 已可直接使用。
> 以下内容面向想修改代码或自行打包的开发者。

### Python 依赖

| 包名 | 用途 |
|---|---|
| **PySide6** (6.11.0) | Qt for Python 绑定，提供完整的 GUI 界面 |
| **python-fsb5** (HearthSim) | FSB5 音频容器解析库 |
| **requests** | HTTP 库，用于网易云音乐 API 调用 |
| **PyInstaller** (6.20.0) | 将 Python 项目打包为独立 EXE |

### 打包命令

```bash
# 创建虚拟环境
python -m venv venv

# 安装依赖
pip install PySide6
pip install git+https://github.com/HearthSim/python-fsb5.git
pip install requests
pip install pyinstaller

# 打包
python build_exe.py
```

打包完成后，`NovaHorizonRadio_v1.0.1.exe` 会生成在当前目录下，与 `tools/` `config/` 等文件夹同级。

---

## 许可证

本项目仅用于学习和研究目的。使用本工具修改游戏文件可能违反游戏服务条款，请自行承担风险。

FMOD Studio API 版权归 Firelight Technologies Pty, Ltd 所有。
FFmpeg 基于 LGPL/GPL 许可证。
