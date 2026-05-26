import sys, os, json, threading, re
from pathlib import Path
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton,
    QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QSplitter, QFrame,
    QComboBox, QAbstractItemView, QListWidget, QListWidgetItem,
)
from PySide6.QtGui import QFont, QIcon, QPalette, QColor, QTextCharFormat, QTextCursor

sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))
from core.engine import NovaHorizonEngine, detect_banks


class ReplaceWorker(QThread):
    progress = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, engine, replace_map, dry_run):
        super().__init__()
        self.engine = engine
        self.replace_map = replace_map
        self.dry_run = dry_run

    def run(self):
        new_data = {}
        total = len(self.replace_map)
        for idx, (file_path, meta) in sorted(self.replace_map.items()):
            self.progress.emit(f"编码 [{idx}] {Path(file_path).name}...")
            try:
                raw = self.engine.encode_song(file_path)
                new_data[idx] = raw
                self.progress.emit(f"  OK {len(raw)/1024/1024:.1f} MB")
            except Exception as e:
                self.progress.emit(f"  FAIL {e}")

        if new_data:
            self.progress.emit(f"\n重建 FSB5 ({len(new_data)}/{total} 首)...")
            try:
                self.engine.rebuild_and_patch(new_data, dry_run=self.dry_run)
                updates = {idx: meta for idx, (_, meta) in self.replace_map.items() if idx in new_data}
                if not self.dry_run and updates:
                    self.engine.update_radio_info(updates)
                    self.progress.emit("OK RadioInfo.xml 已更新")
                mode = "试运行" if self.dry_run else "写入"
                self.finished_signal.emit(True, f"{mode}完成！{len(new_data)} 首替换成功")
            except Exception as e:
                self.finished_signal.emit(False, f"失败：{e}")
        else:
            self.finished_signal.emit(False, "没有成功编码的歌曲")


class AudioFileItemWidget(QWidget):
    def __init__(self, file_info, parent=None):
        super().__init__(parent)
        self.file_info = file_info
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        self.cb = QCheckBox()
        self.cb.setChecked(False)
        layout.addWidget(self.cb)

        info_label = QLabel(f"{self.file_info['name']}")
        info_label.setToolTip(f"路径：{self.file_info['path']}\n大小：{self.file_info['size_str']}")
        layout.addWidget(info_label)
        layout.addStretch()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = NovaHorizonEngine()
        self.song_table_data = []
        self.loaded_audio_files = []
        self.worker = None
        self.available_banks = []
        self.current_bank_name = None
        self._next_assign_slot = 0

        self.setWindowTitle("NovaHorizonRadio v1.0 - 地平线 6 电台音乐替换工具")
        self.setMinimumSize(1300, 850)

        icon_path = Path(__file__).parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._setup_ui()
        self._scan_banks()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        toolbar = QHBoxLayout()

        toolbar.addWidget(QLabel("电台:"))
        self.bank_combo = QComboBox()
        self.bank_combo.setMinimumWidth(260)
        self.bank_combo.currentIndexChanged.connect(self._on_bank_changed)
        toolbar.addWidget(self.bank_combo)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setToolTip("刷新电台列表")
        self.refresh_btn.setMaximumWidth(60)
        self.refresh_btn.clicked.connect(self._scan_banks)
        toolbar.addWidget(self.refresh_btn)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("音频源:"))
        self.playlist_input = QLineEdit()
        self.playlist_input.setPlaceholderText("文件夹路径或网易云歌单链接")
        self.playlist_input.setMinimumWidth(280)
        toolbar.addWidget(self.playlist_input)

        self.browse_btn = QPushButton("浏览")
        self.browse_btn.clicked.connect(self._browse_folder)
        toolbar.addWidget(self.browse_btn)
        self.fetch_btn = QPushButton("网易云")
        self.fetch_btn.clicked.connect(self._fetch_playlist)
        toolbar.addWidget(self.fetch_btn)

        toolbar.addStretch()

        self.extract_btn = QPushButton("提取原曲")
        self.extract_btn.clicked.connect(self._extract_originals)
        self.extract_btn.setMaximumHeight(28)
        toolbar.addWidget(self.extract_btn)

        main_layout.addLayout(toolbar)

        body = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 2, 0)

        log_group = QGroupBox("运行日志")
        log_group.setMaximumWidth(340)
        log_layout = QVBoxLayout(log_group)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(500)
        font = QFont("Consolas", 9)
        self.log_output.setFont(font)
        log_layout.addWidget(self.log_output)
        left_layout.addWidget(log_group)

        body.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_splitter = QSplitter(Qt.Vertical)

        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)

        table_header = QHBoxLayout()
        table_header.addWidget(QLabel("电台内歌曲 (勾选要替换的):"))
        table_header.addStretch()
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setMaximumHeight(24)
        self.select_all_btn.clicked.connect(lambda: self._toggle_all(True))
        table_header.addWidget(self.select_all_btn)
        self.deselect_all_btn = QPushButton("清除")
        self.deselect_all_btn.setMaximumHeight(24)
        self.deselect_all_btn.clicked.connect(lambda: self._toggle_all(False))
        table_header.addWidget(self.deselect_all_btn)
        table_layout.addLayout(table_header)

        self.song_table = QTableWidget()
        self.song_table.setColumnCount(7)
        self.song_table.setHorizontalHeaderLabels(["", "#", "歌曲名", "歌手", "时长", "替换状态", "来源文件"])
        self.song_table.setColumnWidth(0, 34)
        self.song_table.setColumnWidth(1, 32)
        self.song_table.setColumnWidth(2, 260)
        self.song_table.setColumnWidth(3, 160)
        self.song_table.setColumnWidth(4, 56)
        self.song_table.setColumnWidth(5, 140)
        self.song_table.setColumnWidth(6, 220)
        self.song_table.verticalHeader().setVisible(False)
        self.song_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.song_table.setAlternatingRowColors(True)
        self.song_table.setContextMenuPolicy(Qt.CustomContextMenu)
        hdr = self.song_table.horizontalHeader()
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        table_layout.addWidget(self.song_table)

        right_splitter.addWidget(table_widget)

        file_widget = QWidget()
        file_layout = QVBoxLayout(file_widget)
        file_layout.setContentsMargins(0, 0, 0, 0)

        file_header = QHBoxLayout()
        file_header.addWidget(QLabel("已加载的音频文件 (勾选要匹配的):"))
        file_header.addStretch()

        select_files_btn = QPushButton("全选")
        select_files_btn.setMaximumHeight(26)
        select_files_btn.clicked.connect(self._select_all_files)
        file_header.addWidget(select_files_btn)

        clear_files_btn = QPushButton("清除勾选")
        clear_files_btn.setMaximumHeight(26)
        clear_files_btn.clicked.connect(self._clear_file_selection)
        file_header.addWidget(clear_files_btn)

        auto_match_btn = QPushButton("按顺序自动匹配")
        auto_match_btn.setToolTip("将下方已勾选的文件依次填入上方已勾选或空位")
        auto_match_btn.setMaximumHeight(26)
        auto_match_btn.clicked.connect(self._auto_match_files)
        file_header.addWidget(auto_match_btn)

        clear_file_btn = QPushButton("清空列表")
        clear_file_btn.setMaximumHeight(26)
        clear_file_btn.clicked.connect(self._clear_loaded_files)
        file_header.addWidget(clear_file_btn)

        file_layout.addLayout(file_header)

        self.file_list = QListWidget()
        self.file_list.setMinimumHeight(120)
        self.file_list.setSpacing(2)
        file_layout.addWidget(self.file_list)

        right_splitter.addWidget(file_widget)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)

        right_layout.addWidget(right_splitter)

        actions = QHBoxLayout()
        actions.addStretch()
        self.dry_run_cb = QCheckBox("试运行 (仅预览)")
        self.dry_run_cb.setChecked(True)
        actions.addWidget(self.dry_run_cb)

        self.replace_btn = QPushButton("执行替换")
        self.replace_btn.setMinimumHeight(36)
        self.replace_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22; color: white; font-size: 14px;
                font-weight: bold; padding: 4px 24px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #d35400; }
            QPushButton:disabled { background-color: #95a5a6; }
        """)
        self.replace_btn.clicked.connect(self._do_replace)
        actions.addWidget(self.replace_btn)

        right_layout.addLayout(actions)

        body.addWidget(right_widget)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 4)

        main_layout.addWidget(body)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumHeight(10)
        main_layout.addWidget(self.progress_bar)

        self._setup_log_colors()

    def _setup_log_colors(self):
        self.log_info_format = QTextCharFormat()
        self.log_info_format.setForeground(QColor("#4a90d9"))

        self.log_warn_format = QTextCharFormat()
        self.log_warn_format.setForeground(QColor("#f39c12"))

        self.log_error_format = QTextCharFormat()
        self.log_error_format.setForeground(QColor("#e74c3c"))

        self.log_success_format = QTextCharFormat()
        self.log_success_format.setForeground(QColor("#27ae60"))

    def _append_log(self, msg, level="INFO"):
        cursor = self.log_output.textCursor()
        cursor.movePosition(QTextCursor.End)

        if level == "INFO":
            fmt = self.log_info_format
        elif level == "WARNING":
            fmt = self.log_warn_format
        elif level == "ERROR":
            fmt = self.log_error_format
        elif level == "SUCCESS":
            fmt = self.log_success_format
        else:
            fmt = QTextCharFormat()

        cursor.insertText(f"[{level}] ", fmt)
        cursor.insertText(msg + "\n", QTextCharFormat())

        sb = self.log_output.verticalScrollBar()
        sb.setValue(sb.maximum())

    def log(self, msg, level="INFO"):
        self._append_log(msg, level)

    def _scan_banks(self):
        self.log("正在扫描电台...")
        self.available_banks = detect_banks()
        self.bank_combo.blockSignals(True)
        self.bank_combo.clear()
        if not self.available_banks:
            self.log("未找到游戏电台文件！", "ERROR")
            self.bank_combo.addItem("未找到电台")
            self.bank_combo.blockSignals(False)
            return

        for b in self.available_banks:
            label = f"{b['display_name']} ({b['name']})  [{b['size_mb']} MB]"
            self.bank_combo.addItem(label, b["name"])

        self.bank_combo.blockSignals(False)
        self.log(f"发现 {len(self.available_banks)} 个电台", "SUCCESS")
        self._on_bank_changed(0)

    def _on_bank_changed(self, idx):
        if idx < 0 or not self.available_banks:
            return
        bank_name = self.bank_combo.itemData(idx)
        if not bank_name or bank_name == self.current_bank_name:
            return

        self.current_bank_name = bank_name
        self.engine.current_bank = bank_name
        self.log(f"切换到：{self.bank_combo.currentText()}")

        sm = self.engine._load_song_map(bank_name)
        if not sm:
            self.log("首次使用此电台，自动生成歌单映射...")
            sm = self.engine.auto_generate_song_map(bank_name)
            self.log(f"已生成 {len(sm)} 首歌映射", "SUCCESS")

        if not self.engine.verify_mapping(bank_name):
            self.log("警告：映射已偏移，正在重新生成...", "WARNING")
            sm = self.engine.auto_generate_song_map(bank_name)

        self._load_songs_to_table(bank_name)

    def _load_songs_to_table(self, bank_name):
        bi = self.engine.get_bank_info(bank_name)
        self.song_table.setRowCount(bi.num_songs)
        self.song_table_data = []

        for s in bi.songs:
            row = s.index
            cb = QTableWidgetItem()
            cb.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            cb.setCheckState(Qt.CheckState.Unchecked)
            self.song_table.setItem(row, 0, cb)
            self.song_table.setItem(row, 1, QTableWidgetItem(str(s.index)))
            self.song_table.setItem(row, 2, QTableWidgetItem(s.title))
            self.song_table.setItem(row, 3, QTableWidgetItem(s.artist))
            m, sec = divmod(int(s.duration_sec), 60)
            self.song_table.setItem(row, 4, QTableWidgetItem(f"{m}:{sec:02d}"))
            self.song_table.setItem(row, 5, QTableWidgetItem(""))
            self.song_table.setItem(row, 6, QTableWidgetItem(""))
            self.song_table_data.append({"index": s.index, "file": None,
                                          "title": s.title, "artist": s.artist})

    def _toggle_all(self, state: bool):
        for row in range(self.song_table.rowCount()):
            item = self.song_table.item(row, 0)
            if item:
                item.setCheckState(Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择包含音频文件的文件夹")
        if folder:
            self.playlist_input.setText(folder)
            self._load_local_folder(folder)

    def _load_local_folder(self, folder: str):
        path = Path(folder)
        if not path.exists():
            self.log(f"文件夹不存在：{folder}", "ERROR")
            return

        exts = ('.mp3', '.ogg', '.wav', '.flac', '.m4a')
        audio_files = sorted([
            f for f in path.iterdir()
            if f.is_file() and f.suffix.lower() in exts
        ])
        if not audio_files:
            self.log(f"未找到音频文件 ({', '.join(exts)})", "WARNING")
            return

        self.loaded_audio_files = [str(f) for f in audio_files]
        self.file_list.clear()

        for i, f in enumerate(audio_files):
            size_mb = f.stat().st_size / 1024 / 1024
            if size_mb < 1:
                size_str = f"{size_mb*1024:.0f} KB"
            elif size_mb < 100:
                size_str = f"{size_mb:.1f} MB"
            else:
                size_str = f"{size_mb:.0f} MB"

            item = QListWidgetItem()
            widget = AudioFileItemWidget({
                "index": i,
                "path": str(f),
                "name": f.name,
                "size_str": size_str
            })
            widget.cb.setChecked(False)
            item.setSizeHint(widget.sizeHint())
            self.file_list.addItem(item)
            self.file_list.setItemWidget(item, widget)

        self._next_assign_slot = 0
        self.log(f"已加载 {len(audio_files)} 个音频文件 ({folder})", "SUCCESS")

    def _select_all_files(self):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            widget = self.file_list.itemWidget(item)
            if widget:
                widget.cb.setChecked(True)

    def _clear_file_selection(self):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            widget = self.file_list.itemWidget(item)
            if widget:
                widget.cb.setChecked(False)

    def _clear_loaded_files(self):
        self.file_list.clear()
        self.loaded_audio_files = []
        for data in self.song_table_data:
            data["file"] = None
        for row in range(self.song_table.rowCount()):
            self.song_table.item(row, 5).setText("")
            self.song_table.item(row, 6).setText("")
            cb = self.song_table.item(row, 0)
            if cb:
                cb.setCheckState(Qt.CheckState.Unchecked)
        self._next_assign_slot = 0
        self.log("已清空所有文件映射")

    def _get_checked_file_indices(self):
        indices = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            widget = self.file_list.itemWidget(item)
            if widget and widget.cb.isChecked():
                indices.append(i)
        return indices

    def _assign_to_slot(self, file_idx: int, target_row: int):
        if not self.loaded_audio_files or file_idx >= len(self.loaded_audio_files):
            return False
        if target_row < 0 or target_row >= self.song_table.rowCount():
            return False

        file_path = self.loaded_audio_files[file_idx]
        file_name = Path(file_path).name

        self.song_table_data[target_row]["file"] = file_path
        self.song_table.item(target_row, 0).setCheckState(Qt.CheckState.Checked)
        self.song_table.item(target_row, 5).setText("待替换")
        self.song_table.item(target_row, 6).setText(file_name)

        self.log(f"  分配：[{target_row}] <- {file_name}")
        return True

    def _auto_match_files(self):
        checked_indices = self._get_checked_file_indices()
        count = len(checked_indices)
        if count == 0:
            self.log("没有已勾选的音频文件", "WARNING")
            return

        checked_rows = []
        for row in range(self.song_table.rowCount()):
            cb = self.song_table.item(row, 0)
            if cb and cb.checkState() == Qt.CheckState.Checked:
                if not self.song_table_data[row]["file"]:
                    checked_rows.append(row)

        if not checked_rows:
            empty_rows = [r for r in range(self.song_table.rowCount())
                          if not self.song_table_data[r]["file"]]
            if not empty_rows:
                self.log("没有空位可匹配", "WARNING")
                return
            targets = empty_rows[:count]
        else:
            targets = checked_rows[:count]

        assigned = 0
        for i, target_row in enumerate(targets):
            if i < count:
                file_idx = checked_indices[i]
                if self._assign_to_slot(file_idx, target_row):
                    assigned += 1

        self._next_assign_slot = max(
            next((r + 1 for r in range(self.song_table.rowCount())
                 if not self.song_table_data[r]["file"]), self.song_table.rowCount()),
            0
        )
        self.log(f"自动匹配完成：{assigned}/{min(count, len(targets))} 首", "SUCCESS")

    def _fetch_playlist(self):
        text = self.playlist_input.text().strip()
        if not text:
            return

        if Path(text).exists():
            self._load_local_folder(text)
            return

        from core.netease_dl import NeteaseDownloader
        dl = NeteaseDownloader()
        try:
            pid = dl.extract_playlist_id(text)
            self.log(f"正在获取歌单 {pid}...")
            info = dl.get_playlist_info(pid)
            if not info:
                self.log("歌单为空或无法访问", "ERROR")
                return

            dl.output_dir = self.engine.project_dir / "extracted" / f"netease_{pid}"
            self.log(f"歌单：{len(info)} 首歌 (取前 25 首)")
            for t in info[:25]:
                self.log(f"  [{t['index']:2d}] {t['title']} - {t['artist']}")

            downloaded = dl.download_playlist(pid)
            if downloaded:
                self.log(f"已下载 {len(downloaded)} 首", "SUCCESS")
                self._load_local_folder(str(dl.output_dir))
            elif dl.output_dir.exists():
                self._load_local_folder(str(dl.output_dir))
            else:
                self.log("下载未完成，请手动加载文件夹", "WARNING")
        except Exception as e:
            self.log(f"网易云错误：{e}", "ERROR")

    def _extract_originals(self):
        if not self.current_bank_name:
            return
        try:
            self.log("提取原曲...")
            result = self.engine.extract_songs(self.current_bank_name)
            out_dir = self.engine.extracted_dir / self.current_bank_name
            self.log(f"已提取 {len(result)} 首到：{out_dir}", "SUCCESS")
            QMessageBox.information(self, "提取完成", f"已提取 {len(result)} 首歌曲到:\n{out_dir}")
        except Exception as e:
            self.log(f"提取失败：{e}", "ERROR")

    def _do_replace(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "正在执行替换操作...")
            return

        if not self.current_bank_name:
            QMessageBox.warning(self, "提示", "请先选择电台")
            return

        replace_map = {}
        for row in range(self.song_table.rowCount()):
            cb = self.song_table.item(row, 0)
            if cb and cb.checkState() == Qt.CheckState.Checked:
                data = self.song_table_data[row]
                if data["file"]:
                    src_name = Path(data["file"]).stem
                    title = re.sub(r'\s*[-–—]\s*.*$', '', src_name).strip()
                    artist_m = re.search(r'[-–—]\s*(.+)$', src_name)
                    artist = artist_m.group(1).strip() if artist_m else ""
                    replace_map[row] = (data["file"], (title, artist))

        if not replace_map:
            QMessageBox.warning(self, "提示",
                                "没有待替换的歌曲。\n\n操作步骤:\n"
                                "1. 浏览/加载包含音频文件的文件夹\n"
                                "2. 勾选上方要替换的歌曲，或点击「按顺序自动匹配」\n"
                                "3. 确认替换状态列显示「待替换」后执行")
            return

        dry_run = self.dry_run_cb.isChecked()
        mode = "试运行" if dry_run else "实际写入"
        self.log(f"\n{'='*50}")
        self.log(f"开始替换 ({mode}) - {len(replace_map)} 首")
        self.log(f"{'='*50}")

        self.replace_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)

        self.worker = ReplaceWorker(self.engine, replace_map, dry_run)
        self.worker.progress.connect(lambda msg: self.log(msg, "INFO"))
        self.worker.finished_signal.connect(self._on_replace_finished)
        self.worker.start()

    def _on_replace_finished(self, success: bool, msg: str):
        self.progress_bar.setVisible(False)
        self.replace_btn.setEnabled(True)
        self.log(f"\n{'='*50}")
        if success:
            self.log(msg, "SUCCESS")
            self._refresh_table_after_replace()
            self._update_song_map_after_replace()
        else:
            self.log(msg, "ERROR")
        self.log(f"{'='*50}")
        if success:
            QMessageBox.information(self, "完成", msg)

    def _refresh_table_after_replace(self):
        for row in range(self.song_table.rowCount()):
            data = self.song_table_data[row]
            if data.get("file"):
                file_path = data["file"]
                file_name = Path(file_path).name
                src_name = Path(file_path).stem
                title = re.sub(r'\s*[-–—]\s*.*$', '', src_name).strip()
                artist_m = re.search(r'[-–—]\s*(.+)$', src_name)
                artist = artist_m.group(1).strip() if artist_m else ""
                
                self.song_table.item(row, 2).setText(title)
                self.song_table.item(row, 3).setText(artist)
                self.song_table.item(row, 5).setText("已替换")
                self.song_table.item(row, 6).setText(file_name)

    def _update_song_map_after_replace(self):
        sm = self.engine._load_song_map(self.current_bank_name)
        if not sm:
            return
        
        updated = False
        for row in range(self.song_table.rowCount()):
            data = self.song_table_data[row]
            if data.get("file"):
                file_path = data["file"]
                src_name = Path(file_path).stem
                title = re.sub(r'\s*[-–—]\s*.*$', '', src_name).strip()
                artist_m = re.search(r'[-–—]\s*(.+)$', src_name)
                artist = artist_m.group(1).strip() if artist_m else ""
                
                if row < len(sm):
                    sm[row]["title"] = title
                    sm[row]["artist"] = artist
                    updated = True
        
        if updated:
            self.engine._save_song_map(self.current_bank_name, sm)
            self.log(f"已更新 song_map.json ({self.current_bank_name})")


def launch_gui():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#2b2b2b"))
    palette.setColor(QPalette.WindowText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Base, QColor("#3c3c3c"))
    palette.setColor(QPalette.AlternateBase, QColor("#353535"))
    palette.setColor(QPalette.Text, QColor("#e0e0e0"))
    palette.setColor(QPalette.Button, QColor("#4a4a4a"))
    palette.setColor(QPalette.ButtonText, QColor("#e0e0e0"))
    palette.setColor(QPalette.Highlight, QColor("#e67e22"))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
