import sys
import os
import pyzipper
import shutil
import requests
import json
import tempfile
import zipfile
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
    QCheckBox, QComboBox, QGroupBox, QGridLayout, QMessageBox,
    QSpinBox, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QPalette, QColor

class CompressThread(QThread):
    progress = pyqtSignal(int)
    current_file = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, source_path, output_dir, volume_size, password):
        super().__init__()
        self.source_path = source_path
        self.output_dir = output_dir
        self.volume_size = volume_size
        self.password = password
    
    def get_total_size(self, path):
        """计算文件或文件夹的总大小"""
        total = 0
        if os.path.isfile(path):
            total += os.path.getsize(path)
        else:
            for root, dirs, files in os.walk(path):
                for file in files:
                    total += os.path.getsize(os.path.join(root, file))
        return total
    
    def get_files_list(self, path):
        """获取所有文件的列表，包括相对路径，确保没有重复"""
        files = []
        seen_files = set()  # 用于去重
        base_dir = os.path.dirname(path) if os.path.isfile(path) else path
        
        if os.path.isfile(path):
            arcname = os.path.basename(path)
            if arcname not in seen_files:
                files.append((path, arcname))
                seen_files.add(arcname)
        else:
            for root, dirs, file_list in os.walk(path):
                for file in file_list:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, base_dir)
                    if rel_path not in seen_files:
                        files.append((file_path, rel_path))
                        seen_files.add(rel_path)
        return files
    
    def run(self):
        try:
            # 获取源文件/文件夹信息
            source_name = os.path.basename(self.source_path)
            output_base = os.path.join(self.output_dir, source_name)
            
            # 计算总大小和获取文件列表
            total_size = self.get_total_size(self.source_path)
            files_list = self.get_files_list(self.source_path)
            
            if total_size == 0:
                self.finished.emit(False, "源文件或文件夹为空")
                return
            
            # 初始化进度
            processed_size = 0
            
            # 创建临时完整ZIP文件
            temp_zip = f"{output_base}.temp.zip"
            
            # 设置压缩参数
            compression = pyzipper.ZIP_DEFLATED
            
            # 创建完整ZIP文件，使用pyzipper实现可靠的密码保护
            with pyzipper.AESZipFile(
                temp_zip, 'w', 
                compression=compression,
                encryption=pyzipper.WZ_AES if self.password else None
            ) as zipf:
                # 设置密码（如果有）
                if self.password:
                    zipf.setpassword(self.password.encode())
                
                # 压缩所有文件
                for file_path, arcname in files_list:
                    # 发送当前文件名信号
                    self.current_file.emit(arcname)
                    
                    # 获取文件大小
                    file_size = os.path.getsize(file_path)
                    
                    # 压缩文件
                    zipf.write(file_path, arcname)
                    
                    # 更新进度，压缩阶段占90%进度
                    processed_size += file_size
                    # 压缩阶段只到90%，剩下10%留给分卷处理
                    compress_progress = (processed_size / total_size) * 90.0
                    progress = round(compress_progress, 1)
                    self.progress.emit(progress)
            
            # 检查ZIP文件大小
            zip_size = os.path.getsize(temp_zip)
            
            # 如果不需要分卷，直接重命名并完成
            if zip_size <= self.volume_size:
                final_zip = f"{output_base}.zip"
                os.rename(temp_zip, final_zip)
                self.progress.emit(100)
                self.finished.emit(True, f"压缩完成！输出位置：{final_zip}")
                return
            
            # 需要分卷，分割成标准ZIP分卷格式
            # 标准格式：base.zip (最后一个分卷), base.z01, base.z02... (前面的分卷)
            
            # 读取完整ZIP文件内容
            with open(temp_zip, 'rb') as f:
                zip_data = f.read()
            
            # 删除临时文件
            os.remove(temp_zip)
            
            # 计算分卷数量
            num_volumes = (zip_size + self.volume_size - 1) // self.volume_size
            
            # 分割文件成分卷
            volumes = []
            for i in range(num_volumes):
                start = i * self.volume_size
                end = min((i + 1) * self.volume_size, zip_size)
                volume_data = zip_data[start:end]
                
                # 确定分卷文件名
                if i == num_volumes - 1:
                    # 最后一个分卷使用.zip扩展名
                    volume_name = f"{output_base}.zip"
                else:
                    # 前面的分卷使用.z01, .z02...扩展名
                    volume_name = f"{output_base}.z{str(i + 1).zfill(2)}"
                
                # 写入分卷文件
                with open(volume_name, 'wb') as f:
                    f.write(volume_data)
                volumes.append(volume_name)
                
                # 更新进度，分卷处理占10%进度（90%到100%）
                volume_progress = 90.0 + ((i + 1) / num_volumes) * 10.0
                progress = round(volume_progress, 1)
                self.progress.emit(progress)
            
            # 压缩完成
            self.progress.emit(100)
            self.finished.emit(True, f"压缩完成！输出位置：{output_base}.*")
        except Exception as e:
            self.finished.emit(False, f"压缩失败：{str(e)}")

# 更新检测线程
class UpdateCheckThread(QThread):
    update_available = pyqtSignal(str, str)  # 版本号, 下载链接
    no_update = pyqtSignal()
    error = pyqtSignal(str)
    
    def run(self):
        try:
            # 检测GitHub Release中的最新版本
            url = "https://api.github.com/repos/CODMzhuzai/Split-Compression/releases/latest"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            release_data = response.json()
            latest_version = release_data.get("tag_name", "")
            
            # 提取数字版本号（移除可能的前缀）
            if latest_version.startswith("%"):
                latest_version = latest_version[1:]
            
            # 获取下载链接
            assets = release_data.get("assets", [])
            download_url = None
            for asset in assets:
                if asset.get("name", "").endswith(".zip"):
                    download_url = asset.get("browser_download_url")
                    break
            
            if latest_version and download_url:
                self.update_available.emit(latest_version, download_url)
            else:
                self.no_update.emit()
        except Exception as e:
            self.error.emit(str(e))

# 更新下载线程
class UpdateDownloadThread(QThread):
    progress = pyqtSignal(int)  # 进度值 (0-100)
    finished = pyqtSignal(str)  # 下载的文件路径
    error = pyqtSignal(str)
    
    def __init__(self, download_url, save_path):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path
    
    def run(self):
        try:
            response = requests.get(self.download_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get("content-length", 0))
            downloaded_size = 0
            
            with open(self.save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            self.progress.emit(int(progress))
            
            self.finished.emit(self.save_path)
        except Exception as e:
            self.error.emit(str(e))

class VolumeCompressor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_version = "1.01"  # 当前版本
        self.init_ui()
        # 启动时检查更新
        self.check_for_updates()
        
    def init_ui(self):
        # 设置窗口样式
        self.setWindowTitle("分卷压缩工具")
        self.setGeometry(100, 100, 800, 500)
        self.setMinimumSize(1200, 800)
        
        # 设置字体
        font = QFont("Segoe UI", 10)
        self.setFont(font)
        
        # 创建主部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # 源文件选择
        source_group = QGroupBox("源文件/文件夹")
        source_layout = QHBoxLayout()
        
        self.source_line = QLineEdit()
        self.source_line.setPlaceholderText("请选择要压缩的文件或文件夹")
        self.source_line.setReadOnly(True)
        
        source_btn = QPushButton("浏览...")
        source_btn.clicked.connect(self.select_source)
        source_btn.setStyleSheet(self.get_button_style())
        
        source_layout.addWidget(self.source_line, 1)
        source_layout.addWidget(source_btn)
        source_group.setLayout(source_layout)
        main_layout.addWidget(source_group)
        
        # 输出目录选择
        output_group = QGroupBox("输出目录")
        output_layout = QHBoxLayout()
        
        self.output_line = QLineEdit()
        self.output_line.setPlaceholderText("请选择输出目录")
        self.output_line.setReadOnly(True)
        
        output_btn = QPushButton("浏览...")
        output_btn.clicked.connect(self.select_output)
        output_btn.setStyleSheet(self.get_button_style())
        
        output_layout.addWidget(self.output_line, 1)
        output_layout.addWidget(output_btn)
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        # 压缩设置
        settings_group = QGroupBox("压缩设置")
        settings_layout = QGridLayout()
        
        # 分卷大小设置
        settings_layout.addWidget(QLabel("分卷大小："), 0, 0)
        
        size_layout = QHBoxLayout()
        self.size_spin = QDoubleSpinBox()
        self.size_spin.setRange(1, 10240)
        self.size_spin.setValue(100)
        self.size_spin.setSuffix(" MB")
        self.size_spin.setDecimals(0)
        
        self.size_unit = QComboBox()
        self.size_unit.addItems(["MB", "GB"])
        self.size_unit.currentTextChanged.connect(self.update_size_suffix)
        
        size_layout.addWidget(self.size_spin, 1)
        size_layout.addWidget(self.size_unit, 0)
        size_layout.setSpacing(10)
        
        settings_layout.addLayout(size_layout, 0, 1)
        
        # 密码设置
        settings_layout.addWidget(QLabel("密码保护："), 1, 0)
        
        password_layout = QHBoxLayout()
        self.password_check = QCheckBox("设置密码")
        self.password_check.stateChanged.connect(self.toggle_password)
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setEnabled(False)
        
        password_layout.addWidget(self.password_check)
        password_layout.addWidget(self.password_edit, 1)
        
        settings_layout.addLayout(password_layout, 1, 1)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(self.get_progress_style())
        # 设置进度条显示格式为带百分号的小数
        self.progress_bar.setFormat("%p%")
        # 设置进度条的最小值和最大值，支持小数
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(1000)
        main_layout.addWidget(self.progress_bar)
        
        # 当前压缩文件标签
        self.current_file_label = QLabel("准备压缩...")
        self.current_file_label.setAlignment(Qt.AlignCenter)
        self.current_file_label.setStyleSheet("color: #333; font-style: italic;")
        main_layout.addWidget(self.current_file_label)
        
        # 状态标签
        self.status_label = QLabel("就绪")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #666;")
        main_layout.addWidget(self.status_label)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        
        self.compress_btn = QPushButton("开始压缩")
        self.compress_btn.clicked.connect(self.start_compress)
        self.compress_btn.setStyleSheet(self.get_primary_button_style())
        self.compress_btn.setMinimumHeight(40)
        
        clear_btn = QPushButton("清空")
        clear_btn.clicked.connect(self.clear_all)
        clear_btn.setStyleSheet(self.get_button_style())
        clear_btn.setMinimumHeight(40)
        
        button_layout.addWidget(self.compress_btn, 1)
        button_layout.addWidget(clear_btn)
        
        main_layout.addLayout(button_layout)
        
        # 版本号显示
        version_layout = QHBoxLayout()
        self.version_label = QLabel(f"版本：{self.current_version}")
        self.version_label.setStyleSheet("color: #666; font-size: 12px;")
        version_layout.addWidget(self.version_label)
        version_layout.addStretch()  # 推到左边
        main_layout.addLayout(version_layout)
        
        # 设置样式
        self.setStyleSheet(self.get_global_style())
    
    def get_global_style(self):
        return """
            QMainWindow {
                background-color: #f5f5f7;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding: 15px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #333;
            }
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background-color: white;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #007AFF;
                outline: none;
            }
            QPushButton {
                padding: 8px 16px;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                cursor: pointer;
            }
            QCheckBox {
                font-size: 14px;
                color: #333;
            }
            QSpinBox, QDoubleSpinBox, QComboBox {
                padding: 8px 12px;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                background-color: white;
                font-size: 14px;
            }
            QLabel {
                font-size: 14px;
                color: #333;
            }
        """
    
    def get_button_style(self):
        return """
            QPushButton {
                background-color: #f0f0f0;
                color: #333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: #d0d0d0;
            }
        """
    
    def get_primary_button_style(self):
        return """
            QPushButton {
                background-color: #007AFF;
                color: white;
            }
            QPushButton:hover {
                background-color: #0056cc;
            }
            QPushButton:pressed {
                background-color: #004099;
            }
            QPushButton:disabled {
                background-color: #c7c7cc;
                color: #ffffff;
            }
        """
    
    def get_progress_style(self):
        return """
            QProgressBar {
                border: none;
                border-radius: 6px;
                background-color: #e0e0e0;
                height: 10px;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background-color: #007AFF;
            }
        """
    
    def select_source(self):
        # 先尝试选择文件
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择要压缩的文件", "", "所有文件 (*.*)"
        )
        
        if not file_path:
            # 如果没有选择文件，尝试选择文件夹
            file_path = QFileDialog.getExistingDirectory(
                self, "选择要压缩的文件夹", "", QFileDialog.ShowDirsOnly
            )
        
        if file_path:
            self.source_line.setText(file_path)
    
    def select_output(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", ""
        )
        if dir_path:
            self.output_line.setText(dir_path)
    
    def update_size_suffix(self, unit):
        if unit == "MB":
            self.size_spin.setRange(1, 10240)
            self.size_spin.setValue(100)
        else:
            self.size_spin.setRange(1, 10)
            self.size_spin.setValue(1)
        self.size_spin.setSuffix(f" {unit}")
    
    def toggle_password(self, state):
        self.password_edit.setEnabled(state == Qt.Checked)
    
    def start_compress(self):
        # 检查输入
        source_path = self.source_line.text()
        output_dir = self.output_line.text()
        
        if not source_path:
            QMessageBox.warning(self, "警告", "请选择要压缩的文件或文件夹")
            return
        
        if not output_dir:
            QMessageBox.warning(self, "警告", "请选择输出目录")
            return
        
        # 计算分卷大小（转换为字节）
        size_value = self.size_spin.value()
        size_unit = self.size_unit.currentText()
        volume_size = int(size_value * 1024 * 1024)  # MB
        if size_unit == "GB":
            volume_size = int(size_value * 1024 * 1024 * 1024)  # GB
        
        # 获取密码
        password = self.password_edit.text() if self.password_check.isChecked() else None
        
        # 禁用按钮
        self.compress_btn.setEnabled(False)
        self.status_label.setText("正在压缩...")
        
        # 创建压缩线程
        self.compress_thread = CompressThread(source_path, output_dir, volume_size, password)
        self.compress_thread.progress.connect(self.update_progress)
        self.compress_thread.current_file.connect(self.update_current_file)
        self.compress_thread.finished.connect(self.compress_finished)
        self.compress_thread.start()
    
    def update_current_file(self, filename):
        """更新当前压缩文件标签"""
        self.current_file_label.setText(f"正在压缩：{filename}")
    
    def update_progress(self, value):
        # 将浮点数进度值（0-100.0）转换为整数（0-1000）以显示一位小数
        # 确保值在有效范围内，避免溢出错误
        clamped_value = max(0.0, min(100.0, value))
        progress_value = int(clamped_value * 10)
        # 确保进度值在0-1000范围内
        progress_value = max(0, min(1000, progress_value))
        self.progress_bar.setValue(progress_value)
    
    def compress_finished(self, success, message):
        self.compress_btn.setEnabled(True)
        self.status_label.setText("就绪")
        self.current_file_label.setText("准备压缩...")
        
        if success:
            QMessageBox.information(self, "成功", message)
        else:
            QMessageBox.critical(self, "失败", message)
        
        # 重置进度条为0
        self.progress_bar.setValue(0)
    
    def clear_all(self):
        self.source_line.clear()
        self.output_line.clear()
        self.size_spin.setValue(100)
        self.size_unit.setCurrentIndex(0)
        self.password_check.setChecked(False)
        self.password_edit.clear()
        self.progress_bar.setValue(0)
        self.current_file_label.setText("准备压缩...")
        self.status_label.setText("就绪")
    
    def check_for_updates(self):
        """检查更新"""
        self.update_thread = UpdateCheckThread()
        self.update_thread.update_available.connect(self.on_update_available)
        self.update_thread.no_update.connect(self.on_no_update)
        self.update_thread.error.connect(self.on_update_error)
        self.update_thread.start()
    
    def compare_versions(self, version1, version2):
        """比较版本号，返回True如果version1 < version2"""
        try:
            # 将版本号转换为浮点数进行比较
            v1 = float(version1)
            v2 = float(version2)
            return v1 < v2
        except ValueError:
            return False
    
    def on_update_available(self, latest_version, download_url):
        """发现新版本"""
        if self.compare_versions(self.current_version, latest_version):
            # 显示更新对话框，不可取消
            reply = QMessageBox.information(
                self,
                "发现新版本",
                f"当前版本：{self.current_version}\n最新版本：{latest_version}\n\n正在准备下载更新...",
                QMessageBox.Ok,
                QMessageBox.Ok
            )
            
            if reply == QMessageBox.Ok:
                self.download_update(latest_version, download_url)
    
    def on_no_update(self):
        """没有新版本"""
        # 只在调试时显示，实际运行时可以隐藏
        # QMessageBox.information(self, "更新检查", "当前已是最新版本")
        pass
    
    def on_update_error(self, error):
        """更新检查错误"""
        # 只在调试时显示，实际运行时可以隐藏
        # QMessageBox.warning(self, "更新检查失败", f"检查更新时出错：{error}")
        pass
    
    def download_update(self, latest_version, download_url):
        """下载更新"""
        # 创建更新下载对话框
        self.update_progress_dialog = QWidget(self)
        self.update_progress_dialog.setWindowTitle("更新中")
        self.update_progress_dialog.setGeometry(200, 200, 400, 150)
        self.update_progress_dialog.setWindowModality(Qt.ApplicationModal)  # 不可取消
        
        layout = QVBoxLayout()
        
        label = QLabel(f"正在下载更新 {latest_version}...")
        layout.addWidget(label)
        
        self.update_progress_bar = QProgressBar()
        self.update_progress_bar.setRange(0, 100)
        self.update_progress_bar.setValue(0)
        layout.addWidget(self.update_progress_bar)
        
        status_label = QLabel("0%")
        status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_label)
        
        self.update_progress_dialog.setLayout(layout)
        self.update_progress_dialog.show()
        
        # 创建临时文件保存更新包
        temp_dir = tempfile.gettempdir()
        self.update_file = os.path.join(temp_dir, f"update_{latest_version}.zip")
        
        # 开始下载
        self.download_thread = UpdateDownloadThread(download_url, self.update_file)
        self.download_thread.progress.connect(self.update_progress_bar.setValue)
        self.download_thread.progress.connect(lambda value: status_label.setText(f"{value}%"))
        self.download_thread.finished.connect(self.on_update_downloaded)
        self.download_thread.error.connect(self.on_update_download_error)
        self.download_thread.start()
    
    def on_update_downloaded(self, file_path):
        """更新下载完成"""
        try:
            # 关闭下载对话框
            self.update_progress_dialog.close()
            
            # 解压更新包
            temp_dir = tempfile.gettempdir()
            extract_dir = os.path.join(temp_dir, "update_extract")
            if not os.path.exists(extract_dir):
                os.makedirs(extract_dir)
            
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # 查找主程序文件
            main_file = None
            for root, dirs, files in os.walk(extract_dir):
                for file in files:
                    if file == "分卷压缩工具.exe":
                        main_file = os.path.join(root, file)
                        break
                if main_file:
                    break
            
            if main_file:
                # 获取当前程序信息
                current_exe = sys.executable
                current_dir = os.path.dirname(current_exe)
                
                # 新程序路径（放在同一目录下）
                new_exe = os.path.join(current_dir, "分卷压缩工具.exe")
                
                # 关闭当前程序并替换
                QMessageBox.information(
                    self,
                    "更新完成",
                    "更新已成功下载！程序将重启以应用更新。",
                    QMessageBox.Ok,
                    QMessageBox.Ok
                )
                
                # 清理临时文件
                os.remove(file_path)
                
                # 创建更新脚本
                update_script = os.path.join(temp_dir, "update_script.bat")
                with open(update_script, "w") as f:
                    f.write(f"@echo off\n")
                    f.write(f"echo 正在更新程序...\n")
                    f.write(f"timeout /t 2 /nobreak >nul\n")
                    # 替换旧版本
                    f.write(f"if exist \"{current_exe}\" del /f /q \"{current_exe}\"\n")
                    # 将新程序移动到当前程序位置
                    f.write(f"copy /y \"{main_file}\" \"{new_exe}\"\n")
                    # 删除备份文件（如果存在）
                    f.write(f"if exist \"{current_exe}.bak\" del /f /q \"{current_exe}.bak\"\n")
                    # 启动新程序
                    f.write(f"start \"\" \"{new_exe}\"\n")
                    # 清理自身
                    f.write(f"del /f /q \"{update_script}\"\n")
                    # 删除临时解压目录
                    f.write(f"rd /s /q \"{extract_dir}\"\n")
                
                # 退出当前程序并运行更新脚本
                QApplication.quit()
                os.startfile(update_script)
            else:
                QMessageBox.critical(self, "更新失败", "未找到主程序文件")
                # 清理临时文件
                os.remove(file_path)
                shutil.rmtree(extract_dir)
        except Exception as e:
            QMessageBox.critical(self, "更新失败", f"更新安装失败：{str(e)}")
            # 清理临时文件
            try:
                os.remove(file_path)
                shutil.rmtree(extract_dir)
            except:
                pass
    
    def on_update_download_error(self, error):
        """更新下载错误"""
        self.update_progress_dialog.close()
        QMessageBox.critical(self, "下载失败", f"更新下载失败：{error}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VolumeCompressor()
    window.show()
    sys.exit(app.exec_())
