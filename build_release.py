# -*- coding: utf-8 -*-
"""Catact 一键打包：PyInstaller → release 目录 → Inno Setup → 免安装 zip

用法（在 MXBridgeTool 目录下）：
    py -3 build_release.py

产物：
    dist\\Catact.exe
    release\\Catact\\                 便携版目录（exe + 桥 + python32 + README + 启动.bat）
    release\\Catact_<ver>_便携版.zip
    installer\\Catact_Setup_<ver>.exe
    ..\\2_Catact_<ver>_免安装版.zip   （与便携版 zip 内容相同，放到交接包根目录）
"""
import os
import shutil
import subprocess
import sys
import zipfile

VER = "1.0.6"
ROOT = os.path.dirname(os.path.abspath(__file__))
REL = os.path.join(ROOT, "release", "Catact")
ISCC = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"


def step(msg):
    print("\n=== " + msg + " ===", flush=True)


def run(cmd, cwd=ROOT):
    r = subprocess.run(cmd, cwd=cwd)
    if r.returncode != 0:
        sys.exit(f"命令失败（{r.returncode}）：{cmd}")


def main():
    step("1/5 离线自测")
    run([sys.executable, os.path.join(ROOT, "tests", "test_offline.py")])

    step("2/5 PyInstaller 打 Catact.exe")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--onefile", "--windowed", "--name", "Catact",
         "--icon", os.path.join("app", "catact.ico"),
         os.path.join("app", "main.py")])

    step("3/5 组装 release\\Catact")
    os.makedirs(REL, exist_ok=True)
    shutil.copy2(os.path.join(ROOT, "dist", "Catact.exe"), os.path.join(REL, "Catact.exe"))
    shutil.copy2(os.path.join(ROOT, "app", "mx_bridge.py"), os.path.join(REL, "mx_bridge.py"))
    shutil.copy2(os.path.join(ROOT, "app", "catact.ico"), os.path.join(REL, "catact.ico"))
    shutil.copy2(os.path.join(ROOT, "README.txt"), os.path.join(REL, "README.txt"))
    src_py = os.path.join(ROOT, "app", "python32")
    if not os.path.isdir(os.path.join(REL, "python32")):
        shutil.copytree(src_py, os.path.join(REL, "python32"))
    print("release\\Catact 已更新")

    step("4/5 Inno Setup 打安装包")
    if os.path.exists(ISCC):
        run([ISCC, "Catact.iss"])
    else:
        print("跳过：没找到", ISCC)

    step("5/5 打免安装 zip")
    os.makedirs(os.path.join(ROOT, "release"), exist_ok=True)
    portable = os.path.join(ROOT, "release", f"Catact_{VER}_便携版.zip")
    skip = {"config.json", "modbus_debug.log", "modbus_debug.log.1"}
    n = 0
    with zipfile.ZipFile(portable, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for base, dirs, files in os.walk(REL):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in files:
                if name in skip:
                    continue
                full = os.path.join(base, name)
                arc = os.path.join("Catact", os.path.relpath(full, REL)).replace("\\", "/")
                z.write(full, arc)
                n += 1
    top = os.path.abspath(os.path.join(ROOT, "..", f"2_Catact_{VER}_免安装版.zip"))
    shutil.copy2(portable, top)
    print(f"{n} 个文件 → {portable}")
    print(f"已复制 → {top}")

    step("完成")
    for p in (os.path.join(ROOT, "dist", "Catact.exe"), portable,
              os.path.join(ROOT, "installer", f"Catact_Setup_{VER}.exe"), top):
        print(f"{os.path.getsize(p) / 1048576:6.1f} MB  {p}")


if __name__ == "__main__":
    main()
