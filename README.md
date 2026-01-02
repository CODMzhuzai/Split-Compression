## Split Compression-分卷压缩

一个现代化的分卷压缩GUI程序，支持自定义分卷大小、密码保护和实时进度显示。


## 打包好的程序已放在发行版中的beta标签内

# 我的标题 <a href="https://example.com"><img src="https://github.com/user-attachments/assets/9c9adb5c-1213-4885-a363-39e04573be23" alt="https://github.com/CODMzhuzai/Split-Compression/releases" width="69" height="32"/></a>

<img width="1229" height="534" alt="发行版中的beta标签内" src="https://github.com/user-attachments/assets/1abf3aaf-1c3e-4aa8-a16e-717c18824904" />

## 功能特性

- 📁 支持压缩单个文件或整个文件夹
- 📊 可自定义分卷大小（MB/GB）
- 🔒 支持AES-256密码保护
- 🎨 现代化的界面设计
- 📈 实时压缩进度显示，带百分号和小数点后一位
- 📄 显示当前正在压缩的文件名
- 🛡️ 多线程压缩，不阻塞主线程
- 📦 标准ZIP分卷格式，兼容主流解压软件
- 🚀 自动去重，避免重复文件名警告
- ⚡ 高效DEFLATED压缩算法

## 技术栈

- Python 3.12+
- PyQt5 - 现代化GUI框架
- pyzipper - ZIP格式分卷压缩与AES加密

## 安装依赖

```bash
pip install pyqt5 pyzipper
```

## 使用方法

1. 运行程序：
   ```bash
   python 分卷压缩工具.py
   ```

2. 选择要压缩的文件或文件夹
3. 选择输出目录
4. 设置分卷大小（默认100MB）
5. 可选：设置密码保护（AES-256加密）
6. 点击"开始压缩"按钮
7. 查看实时进度和当前压缩文件
8. 等待压缩完成

## 压缩格式

- 输出格式：标准ZIP分卷压缩
- 文件名格式：`源文件名.z01`, `源文件名.z02`, ..., `源文件名.zip`
- 加密方式：AES-256（当设置密码时）
- 压缩级别：DEFLATED（高效压缩）
- 分卷顺序：前N-1个分卷使用.z01, .z02...扩展名，最后一个分卷使用.zip扩展名

## 界面预览

<img width="1202" height="832" alt="界面预览" src="https://github.com/user-attachments/assets/9a46f4fa-8eaf-4408-a916-4b22efadb88e" />


## 注意事项

1. 压缩过程中请勿关闭程序
2. 密码保护使用AES-256加密，密码丢失将无法恢复
3. 建议根据存储设备的文件系统选择合适的分卷大小
4. 大文件压缩可能需要较长时间，请耐心等待
5. 生成的分卷文件需放在同一目录下才能正常解压
6. 支持使用7-Zip、WinRAR等主流解压软件解压
7. 分卷大小设置范围：10MB - 100GB
8. 自动去重功能会跳过重复文件名，确保压缩包内文件名唯一

## 系统要求

- Windows 10/11
- Python 3.12或更高版本
- 至少1GB可用内存
- 足够的临时存储空间（用于创建临时ZIP文件）

## 许可证

MIT License
