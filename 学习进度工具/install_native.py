"""将已验证的应用安装到固定位置；更新时保留上一版以便回退。"""
import plistlib
import shutil
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "学习进度.app"
DESTINATION = Path("/Applications/研习手记.app")
IDENTIFIER = "local.learning.study-progress"


def verify(app):
    with (app / 'Contents/Info.plist').open('rb') as file:
        info = plistlib.load(file)
    if info.get('CFBundleIdentifier') != IDENTIFIER:
        raise RuntimeError(f'拒绝替换其他应用：{app}')
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)


def running():
    result = subprocess.run(['ps', '-axo', 'comm='], text=True, capture_output=True, check=True)
    executables = {str(p / 'Contents/MacOS/StudyProgress') for p in [SOURCE, DESTINATION]}
    return any(line.strip() in executables for line in result.stdout.splitlines())


def install():
    verify(SOURCE)
    if DESTINATION.is_symlink():
        raise RuntimeError('目标应用是符号链接，停止安装以避免替换错误位置。')
    if DESTINATION.exists():
        verify(DESTINATION)
    # 通过应用自己的退出处理保护未保存输入，不强制终止进程。
    subprocess.run(['osascript', '-e', f'if application id "{IDENTIFIER}" is running then tell application id "{IDENTIFIER}" to quit'], check=True)
    deadline = time.monotonic() + 30
    while running():
        if time.monotonic() >= deadline:
            raise RuntimeError('应用尚未退出，可能有未保存内容。请保存并退出后重新运行安装。')
        time.sleep(0.3)
    stage = DESTINATION.parent / f'.研习手记-install-{uuid.uuid4().hex}.app'
    previous = None
    try:
        shutil.copytree(SOURCE, stage, symlinks=True)
        verify(stage)
        if DESTINATION.exists():
            backup_dir = ROOT / '.native-build' / 'installed-backups'
            backup_dir.mkdir(parents=True, exist_ok=True)
            previous = backup_dir / f'研习手记-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}.app'
            shutil.move(str(DESTINATION), str(previous))
        try:
            stage.rename(DESTINATION)
        except OSError:
            if previous is not None:
                shutil.move(str(previous), str(DESTINATION))
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    print(f'已安装：{DESTINATION}')
    if previous:
        print(f'旧版备份：{previous}')


if __name__ == '__main__':
    install()
