"""使用本机 Swift 编译器构建原生 macOS 应用。"""
import plistlib
import argparse
import json
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='构建并更新应用程序目录中的研习手记')
parser.add_argument('--no-install', action='store_true', help='仅生成项目中的应用，不安装')
args = parser.parse_args()
app = root / "学习进度.app"
contents = app / "Contents"
(contents / "MacOS").mkdir(parents=True, exist_ok=True)
(contents / "Resources").mkdir(exist_ok=True)
# 本机 CLT 同时包含旧、新 SwiftBridging 定义，用构建目录的虚拟覆盖消除重复。
# 不修改 /Library 下的系统文件。
build = root / '.native-build'
build.mkdir(exist_ok=True)
empty = build / 'empty.modulemap'
empty.write_text('// 本次构建忽略重复的旧模块定义。\n')
overlay = build / 'overlay.json'
overlay.write_text(json.dumps({'version': 0, 'roots': [{'type': 'file', 'name': '/Library/Developer/CommandLineTools/usr/include/swift/module.modulemap', 'external-contents': str(empty)}]}))
subprocess.run(["xcrun", "swiftc", "-parse-as-library", "-target", "arm64-apple-macosx14.0", '-vfsoverlay', str(overlay), '-Xcc', '-ivfsoverlay', '-Xcc', str(overlay), "-O", str(root / "StudyApp.swift"), str(root / "Presentation.swift"), str(root / "StudyTheme.swift"), str(root / "EvidenceView.swift"), str(root / "ImageAttachments.swift"), str(root / "MarkdownNotes.swift"), "-o", str(contents / "MacOS/StudyProgress"), "-framework", "SwiftUI", "-framework", "AppKit"], check=True)
for name in ["native_bridge.py", "server.py"]:
    shutil.copy2(root / name, contents / "Resources" / name)
iconset = build / 'StudyIcon.iconset'
iconset.mkdir(exist_ok=True)
icon_drawer = build / 'draw-icon'
subprocess.run(['xcrun', 'swiftc', '-vfsoverlay', str(overlay), '-Xcc', '-ivfsoverlay', '-Xcc', str(overlay), str(root / 'Assets/DrawIcon.swift'), '-o', str(icon_drawer), '-framework', 'AppKit'], check=True)
subprocess.run([str(icon_drawer), str(iconset)], check=True)
subprocess.run(['iconutil', '-c', 'icns', str(iconset), '-o', str(contents / 'Resources/StudyIcon.icns')], check=True)
info = dict(CFBundleName="研习手记", CFBundleDisplayName="研习手记", CFBundleIdentifier="local.learning.study-progress", CFBundleVersion="2", CFBundleShortVersionString="1.1", CFBundlePackageType="APPL", CFBundleExecutable="StudyProgress", NSHighResolutionCapable=True, LSMinimumSystemVersion="14.0", StudyPlanRoot=str(root.parent / "00-索引与面试/AI应用后端三个月复习"))
with (contents / "Info.plist").open("wb") as file:
    info['CFBundleIconFile'] = 'StudyIcon'
    plistlib.dump(info, file)
subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True)
subprocess.run([str(contents / 'MacOS/StudyProgress'), '--check'], check=True)
print(app)
if not args.no_install:
    from install_native import install
    install()
