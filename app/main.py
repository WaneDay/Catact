# -*- coding: utf-8 -*-
"""
Catact（FX5U 仿真 ⇄ 威纶通 EBPro 桥接工具）  v6

UI 参考凌一 PLC 模拟器：
  · 扁平工具栏 + 互斥的启动/停止 + 状态灯
  · 一排扁平的软元件按钮，点开/再点收起
  · 子窗口用系统原生 Toplevel：原生标题栏，拖动由系统接管，无残影
  · 工作区显示已开窗口列表 + 地址速查表
  · 日志区可用分隔条上下拖动改变高度
"""

import json
import os
import queue
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import winreg
from tkinter import ttk, messagebox, filedialog

try:
    import ctypes
    _user32 = ctypes.windll.user32
except Exception:
    _user32 = None

# SetWindowPos 标志：不改变大小 / 不改 Z 序 / 不抢焦点
_SWP_MOVE_ONLY = 0x0001 | 0x0004 | 0x0010


def light_titlebar(win):
    """把窗口标题栏切成浅色，和 GX Works 风格的浅灰界面统一。"""
    if _user32 is None:
        return
    try:
        hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
        val = ctypes.c_int(0)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(val), ctypes.sizeof(val)) == 0:
                break
    except Exception:
        pass


def move_window_fast(win, x, y):
    """用 Win32 SetWindowPos 移动窗口，绕开 Tk geometry 的 Tcl 脚本层，拖动时更顺滑。"""
    if _user32 is None:
        win.geometry("+%d+%d" % (x, y))
        return
    try:
        hwnd = _user32.GetParent(win.winfo_id()) or win.winfo_id()
        _user32.SetWindowPos(hwnd, 0, x, y, 0, 0, _SWP_MOVE_ONLY)
    except Exception:
        pass


def enable_dpi():
    """声明高 DPI 感知。没有它，Windows 会把整个窗口位图拉伸放大，字都是糊的。
    返回实际 DPI（96 = 100% 缩放）。必须在创建任何窗口之前调用。"""
    if _user32 is None:
        return 96
    try:
        # Per-Monitor V2（Win10 1703+）→ Per-Monitor → System，逐级降级
        if not _user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                _user32.SetProcessDPIAware()
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                _user32.SetProcessDPIAware()
            except Exception:
                pass
    # 取实际 DPI
    try:
        dpi = _user32.GetDpiForSystem()
        if dpi:
            return dpi
    except Exception:
        pass
    try:
        hdc = _user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
        _user32.ReleaseDC(0, hdc)
        if dpi:
            return dpi
    except Exception:
        pass
    return 96


DPI = enable_dpi()
S = DPI / 96.0   # 像素尺寸缩放系数（1.0 = 100%，1.25 = 125%，1.5 = 150%）


APP_VERSION = "1.0.6"

# 界面语言：默认中文；Options → Language 可切到现在的英文
LANG = "zh"
UI_FONT_FAMILY = "Segoe UI"

_TR = {
    "en": {
        "app_title": "Catact {ver} - FX5U Modbus Bridge",
        "menu_file": "File", "menu_start": "Start Bridge",
        "menu_stop": "Stop Bridge", "menu_refresh": "Refresh Link",
        "menu_export": "Export Monitor Data...", "menu_exit": "Exit",
        "menu_edit": "Edit", "menu_clear": "Clear Log",
        "menu_convert": "Address Converter...", "menu_close_all": "Close All Windows",
        "menu_view": "View", "menu_device_monitor": "Device Monitor",
        "menu_dev_monitor": "{dev} Monitor", "menu_show_log": "Show Write Log",
        "menu_show_addr": "Show Address Reference", "menu_options": "Options",
        "menu_bridge_settings": "Bridge Settings...",
        "menu_mx_check": "MX Environment Check",
        "menu_station_tool": "Station Setting Tool...",
        "menu_language": "Language", "menu_help": "Help",
        "menu_usage": "Usage", "menu_about": "About",
        "tb_new": "\u25a4 New", "tb_open": "\u25a3 Open", "tb_save": "\u25a5 Save",
        "tb_run": "\u25b6 Run", "tb_stop": "\u25a0 Stop", "tb_reset": "\u21ba Reset",
        "port": "Port", "station": "St", "sim": "Sim",
        "not_started": "Not started", "detecting": "Checking...",
        "project": "Project", "tree_root": "Catact Project",
        "tree_bridge": "\u25a3 Bridge", "tree_control": "Control",
        "tree_sim": "Simulation", "tree_settings": "Settings",
        "tree_devices": "\u25a4 Devices", "tree_diag": "\u25a5 Diagnostics",
        "tree_write_log": "Write Log", "tree_addr_map": "Address Map",
        "tree_help": "? Help", "tree_usage": "Usage", "tree_about": "About",
        "mx_group": " MX Environment ",
        "mx_open": "Open MX Utility", "mx_locate": "Locate...",
        "mx_recheck": "Recheck",
        "mx_installed": "MX Component: Installed",
        "mx_missing": "MX Component: Not detected",
        "mx_notfound": "Communication Settings Utility not found  \u2192  "
                      "click Locate... to pick ActComm.exe",
        "dev_group": " Device Monitor ", "dev_label": "Device",
        "addr_btn": "Addr...",
        "y_group": " Y Output ",
        "win_group": " Monitor Windows ",
        "win_hint": "Double-click a device in the tree to open / close.",
        "wins_open": "{n} monitor window(s) open",
        "no_wins": "No monitor window open",
        "win_tip": "Double-click a device (M / X / Y / D ...) in the Project tree\n"
                   "to open its monitor window; double-click again to close.\n\n"
                   "\u00b7 1 = green cell, 0 = white cell\n"
                   "\u00b7 Right-click a cell: 0x set 1 / set 0, 4x write value\n"
                   "\u00b7 Click a cell: copy \"device = EBPro address\"",
        "addr_group": " Address Reference ",
        "addr_note1": "EBPro area + start address; nth point = start + n - 1",
        "addr_note2": "X/Y octal; W/B/SB/SW hex; others decimal. 1x is read-only.",
        "addr_note3": "Use 0x for switches: X0 -> 0x 10001, X1 -> 0x 10002, "
                      "Y10 -> 0x 11009",
        "monitor_title": "{dev}{start}\u2013{end} ({count} pts)",
        "log_group": " Write Log ",
        "close": "Close", "front": "Front", "ready": "Ready",
        "status_bridge_running": "Bridge: Running",
        "status_bridge_stopped": "Bridge: Stopped",
        "status_mode": "Mode: Auto Reconnect",
        "status_alarms": "Alarms: {n}",
        "status_addr": "Addr: {host}:{port} / St {station}",
        "conn_connected": "Connected", "conn_waiting": "Waiting for sim...",
        "conn_connecting": "Connecting...", "conn_starting": "Starting...",
        "conn_port_busy": "Port in use", "conn_not_started": "Not started",
        "sim_running": "Running", "sim_not_running": "Not running",
        "proc_running": "Running", "proc_stopped": "Stopped",
        "hint_dev": "{dev} monitor - double-click to open/close",
        "hint_log": "Write log - double-click to bring it up",
        "hint_addr": "Address reference - double-click to show",
        "hint_key": "{kind} / {val}",
        "bridge_status_title": "Bridge Control",
        "bridge_status_body": "Bridge process : {proc}\n"
                              "Listen address : {addr}\n"
                              "Logical station: {station}\n"
                              "MX session     : {mx}\n\n"
                              "Use File -> Start/Stop/Refresh, or the toolbar.",
        "sim_status_title": "Simulation",
        "sim_status_body": "GX Simulator3 : {sim}\n"
                           "Auto reconnect: Enabled\n\n"
                           "Start or stop the GX simulation at any time; the bridge "
                           "watches FSimRun3.exe and rebuilds the MX session "
                           "automatically.",
        "bridge_settings_title": "Bridge Settings",
        "port_setting": "Listen Port / Port",
        "station_setting": "MX Logical Station / Station",
        "save": "Save",
        "err_int": "Port and station must be integers",
        "export_title": "Export",
        "no_window": "Open a monitor window first",
        "usage_title": "Usage",
        "about_title": "About",
        "mx_dialog_title": "MX Utility",
        "mx_not_found_msg": "Communication Settings Utility (ActComm.exe) was not "
                            "found automatically.\n\nLocate it manually now? "
                            "Catact will remember the path for one-click launch.",
        "mx_not_actcomm": "You selected:\n{name}\n\nIt is not ActComm.exe. "
                          "Use it as the MX setting tool anyway?",
        "mx_locate_title": "Locate ActComm.exe",
        "mx_open_fail": "Open failed: {err}",
        "mx_check_title": "MX Environment",
        "mx_check_extra": "Use Open MX Utility on the right to launch it.",
        "installed": "Installed", "not_installed": "Not installed",
        "ready": "Ready", "missing": "Missing",
        "path_missing": "Not found (click Open MX Utility to locate)",
        "mx_utility_label": "Utility",
        "python_label": "32-bit Python", "sim_label": "GX Simulator",
        "sim_ok": "Running", "sim_none": "Not detected",
        "lang_restart_title": "Switch Language",
        "lang_restart_msg": "Language switched to English.\n\n"
                            "Catact must restart to apply. Restart now?",
        "lang_restart_fail": "Restart failed. Please close and reopen Catact.",
        "lang_save_fail": "Cannot save config.json (folder not writable). Language not changed.",
        "help_body": "Start\n"
                     "1. GX Works3: open an FX5U project -> Debug -> Start Simulation "
                     "(the bridge may be started before or after)\n"
                     "2. Toolbar Run starts the bridge; Stop stops it; Reset reconnects\n"
                     "3. Port / St show the listen port and logical station; Sim LED "
                     "shows GX simulation state\n\n"
                     "UI\n"
                     "4. Left Project tree: Bridge (Control/Simulation/Settings), "
                     "Devices (M/X/Y/D...), Diagnostics\n"
                     "5. Double-click a device to open its monitor window; double-click "
                     "again to close. View -> Device Monitor also works\n"
                     "6. Status bar: Bridge / Addr / Mode / Alarms / Time\n\n"
                     "EBPro\n"
                     "7. Device: MODBUS TCP/IP, IP 127.0.0.1, port 502, station 1\n"
                     "8. Check addresses with Edit -> Address Converter: M0 -> 0x 1, "
                     "X0 -> 0x 10001, Y10 -> 0x 11009\n"
                     "9. After pressing a button, read Write Log: [write] reached the "
                     "bridge; [write not effective] PLC rejected it; [address hint] "
                     "the switch is bound to 1x, change it to 0x\n\n"
                     "Auto reconnect\n"
                     "10. The bridge may stay open; it reconnects automatically after "
                     "GX simulation stop/start/restart\n"
                     "11. If it does not reconnect, click Reset; no need to stop and "
                     "start the bridge",
        "about_body": "Catact {ver}\n\n"
                      "FX5U simulation <-> Weintek EBPro\n"
                      "MX Component -> Modbus TCP bridge\n\n"
                      "v1.0.6: language setting (Chinese default / English), "
                      "Chinese UI font, MX Environment one-click utility.\n"
                      "Keeps 1.0.4 button interlock, live simulation detection and "
                      "auto reconnect.",
    },
    "zh": {
        "app_title": "Catact {ver} - FX5U Modbus 桥",
        "menu_file": "文件", "menu_start": "启动桥",
        "menu_stop": "停止桥", "menu_refresh": "刷新连接",
        "menu_export": "导出监视数据…", "menu_exit": "退出",
        "menu_edit": "编辑", "menu_clear": "清空日志",
        "menu_convert": "地址换算…", "menu_close_all": "关闭全部窗口",
        "menu_view": "视图", "menu_device_monitor": "元件监视",
        "menu_dev_monitor": "{dev} 监视", "menu_show_log": "显示写入日志",
        "menu_show_addr": "显示地址参考", "menu_options": "选项",
        "menu_bridge_settings": "桥参数…",
        "menu_mx_check": "MX 环境检查",
        "menu_station_tool": "站号设置工具…",
        "menu_language": "语言", "menu_help": "帮助",
        "menu_usage": "使用说明", "menu_about": "关于",
        "tb_new": "▤ 清空", "tb_open": "▣ 换算", "tb_save": "▥ 导出",
        "tb_run": "▶ 启动", "tb_stop": "■ 停止", "tb_reset": "↺ 重连",
        "port": "端口", "station": "站号", "sim": "仿真",
        "not_started": "未启动", "detecting": "检测中…",
        "project": "工程", "tree_root": "Catact 工程",
        "tree_bridge": "▣ 桥", "tree_control": "控制",
        "tree_sim": "仿真", "tree_settings": "设置",
        "tree_devices": "▤ 元件", "tree_diag": "▥ 诊断",
        "tree_write_log": "写入日志", "tree_addr_map": "地址表",
        "tree_help": "? 帮助", "tree_usage": "使用说明", "tree_about": "关于",
        "mx_group": " MX 环境 ",
        "mx_open": "打开 MX 工具", "mx_locate": "定位…", "mx_recheck": "重新检测",
        "mx_installed": "MX Component：已安装",
        "mx_missing": "MX Component：未检测到",
        "mx_notfound": "未找到 Communication Settings Utility  →  "
                       "点「定位…」手动选择 ActComm.exe",
        "dev_group": " 元件监视 ", "dev_label": "元件", "addr_btn": "地址…",
        "y_group": " Y 输出 ",
        "win_group": " 监视窗口 ",
        "win_hint": "双击左侧工程树里的元件打开 / 关闭。",
        "wins_open": "已打开 {n} 个监视窗口",
        "no_wins": "没有打开的监视窗口",
        "win_tip": "双击工程树里的元件（M / X / Y / D …）打开监视窗口，\n"
                   "再双击关闭。\n\n"
                   "· 1 = 绿格，0 = 白格\n"
                   "· 右键格子：0x 置 1 / 置 0，4x 写入数值\n"
                   "· 单击格子：复制「元件 = EBPro 地址」",
        "addr_group": " 地址参考 ",
        "addr_note1": "EBPro 区号 + 起始地址；第 n 个点 = 起始 + n - 1",
        "addr_note2": "X/Y 八进制；W/B/SB/SW 十六进制；其余十进制。1x 只读。",
        "addr_note3": "开关用 0x：X0 → 0x 10001，X1 → 0x 10002，Y10 → 0x 11009",
        "log_group": " 写入日志 ",
        "monitor_title": "{dev}{start}–{end}（{count} 点）",
        "close": "关闭", "front": "前置", "ready": "就绪",
        "status_bridge_running": "桥：运行中",
        "status_bridge_stopped": "桥：已停止",
        "status_mode": "模式：自动重连",
        "status_alarms": "报警：{n}",
        "status_addr": "地址：{host}:{port} / 站 {station}",
        "conn_connected": "已连接", "conn_waiting": "等待仿真…",
        "conn_connecting": "连接中…", "conn_starting": "启动中…",
        "conn_port_busy": "端口占用", "conn_not_started": "未启动",
        "sim_running": "运行中", "sim_not_running": "未运行",
        "proc_running": "运行中", "proc_stopped": "已停止",
        "hint_dev": "{dev} 监视 - 双击打开/关闭",
        "hint_log": "写入日志 - 双击显示",
        "hint_addr": "地址参考 - 双击显示",
        "hint_key": "{kind} / {val}",
        "bridge_status_title": "桥控制",
        "bridge_status_body": "桥进程：{proc}\n监听地址：{addr}\n"
                              "逻辑站号：{station}\nMX 会话：{mx}\n\n"
                              "用 文件 → 启动/停止/刷新，或工具栏按钮。",
        "sim_status_title": "仿真状态",
        "sim_status_body": "GX Simulator3：{sim}\n自动重连：已启用\n\n"
                           "随时启动或停止 GX 仿真；桥会监视 FSimRun3.exe 并"
                           "自动重建 MX 会话。",
        "bridge_settings_title": "桥参数",
        "port_setting": "监听端口 / Port",
        "station_setting": "MX 逻辑站号 / Station",
        "save": "保存",
        "err_int": "端口和站号必须是整数",
        "export_title": "导出",
        "no_window": "先打开一个监视窗口",
        "usage_title": "使用说明",
        "about_title": "关于",
        "mx_dialog_title": "MX 工具",
        "mx_not_found_msg": "没有自动找到 Communication Settings Utility"
                            "（ActComm.exe）。\n\n是否现在手动定位？定位一次后"
                            "程序会记住路径，以后一键打开。",
        "mx_not_actcomm": "你选的是：\n{name}\n\n它不是 ActComm.exe。仍要把它"
                          "记作 MX 设置工具吗？",
        "mx_locate_title": "定位 ActComm.exe",
        "mx_open_fail": "打开失败：{err}",
        "mx_check_title": "MX 环境",
        "mx_check_extra": "右侧「打开 MX 工具」可一键打开设置工具。",
        "installed": "已安装", "not_installed": "未安装",
        "ready": "就绪", "missing": "缺失",
        "path_missing": "未找到（点「打开 MX 工具」可手动定位）",
        "mx_utility_label": "设置工具",
        "python_label": "32 位 Python", "sim_label": "GX 仿真器",
        "sim_ok": "运行中", "sim_none": "未检测到",
        "lang_restart_title": "切换语言",
        "lang_restart_msg": "语言已切换为中文。\n\n需要重启 Catact 才能完整"
                            "生效，是否现在重启？",
        "lang_restart_fail": "重启失败，请手动关闭后重新打开 Catact。",
        "lang_save_fail": "无法写入 config.json（目录不可写），语言未切换。",
        "help_body": "【启动】\n"
                     "1. GX Works3 打开 FX5U 工程 → 调试 → 模拟开始"
                     "（桥可以后开，也可以先开）\n"
                     "2. 点工具栏「▶ 启动」启动桥；「■ 停止」停止；"
                     "「↺ 重连」手动重连\n"
                     "3. 工具栏右侧 端口 / 站号 显示监听端口和逻辑站号，"
                     "仿真灯显示 GX 仿真状态\n\n"
                     "【界面】\n"
                     "4. 左侧工程树：桥（控制/仿真/设置）、元件"
                     "（M/X/Y/D…）、诊断\n"
                     "5. 双击元件名打开监视窗口，再双击关闭；"
                     "也可用 视图 → 元件监视\n"
                     "6. 底部状态栏：桥 / 地址 / 模式 / 报警 / 时间\n\n"
                     "【EBPro】\n"
                     "7. 设备类型 MODBUS TCP/IP，IP 127.0.0.1，端口 502，站号 1\n"
                     "8. 地址用 编辑 → 地址换算 查：M0 → 0x 1，"
                     "X0 → 0x 10001，Y10 → 0x 11009\n"
                     "9. 按钮按下去看写入日志： [写入] 已到桥；"
                     "[写入未生效] PLC 不接受；\n"
                     "   [地址提示] 开关绑到了 1x，请改用 0x 地址\n\n"
                     "【自动重连】\n"
                     "10. 桥可以一直开着；GX 仿真停止/启动/重启后会自动重新连接\n"
                     "11. 万一没自动连上，点「↺ 重连」手动重连，"
                     "不用停止桥再启动",
        "about_body": "Catact {ver}\n\n"
                      "FX5U 仿真 ⇄ 威纶通 EBPro\n"
                      "MX Component → Modbus TCP 桥接\n\n"
                      "v1.0.6：新增语言设置（默认中文 / 可切英文）、中文界面字体、"
                      "MX 环境一键打开。\n"
                      "保留 1.0.4 的按钮互斥、仿真实时检测与自动重连。",
    },
}


def T(key, **kw):
    """取当前语言的界面文案；缺键时回退英文。"""
    table = _TR.get(LANG) or _TR["en"]
    s = table.get(key)
    if s is None:
        s = _TR["en"].get(key, key)
    return s.format(**kw) if kw else s


APP_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):   # PyInstaller 打包后：用 exe 所在目录
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
BRIDGE_SCRIPT = os.path.join(APP_DIR, "mx_bridge.py")
ICON_PATH = os.path.join(APP_DIR, "catact.ico")
# 与 mx_bridge.py 约定的重连信号文件：写它 = 请求桥立即重连 GX 仿真
LINK_REQ_PATH = os.path.join(APP_DIR, "link.req")

DEFAULT_CFG = {
    "python32": os.path.join(APP_DIR, "python32", "python.exe"),
    "host": "127.0.0.1",
    "port": 502,
    "station": 1,
    "refresh_ms": 400,
    "lang": "zh",              # zh=中文（默认），en=English
    "mx_utility": "",          # 手动定位过的 ActComm.exe 路径，记住下次直接用
}

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

def parse_proc_table(text):
    """解析 PowerShell 吐出的进程表（TSV：pid / ppid / name / exe / cmdline）。"""
    rows = []
    for line in (text or "").splitlines():
        parts = line.rstrip("\r\n").split("\t")
        if len(parts) < 5:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        rows.append({"pid": pid, "ppid": ppid, "name": parts[2].strip(),
                     "exe": parts[3].strip(), "cmd": parts[4]})
    return rows


# 这些都是「终端/解释器」类父进程：从它们启动的桥属于手动运行，和 GUI 残留一样可以清理。
# 其余父进程（Catact.exe 或用户改过名的 Catact）视为「另一个实例正在用」，不能杀。
_CONSOLE_PARENTS = {
    "python.exe", "pythonw.exe", "py.exe",
    "cmd.exe", "powershell.exe", "pwsh.exe",
    "conhost.exe", "windowsterminal.exe",
}


def classify_bridge_procs(rows, port, self_pid=0):
    """把桥进程分成两类：
      orphans —— 父进程已经没了（或父进程是终端/解释器），是上一次残留的，可以安全结束；
      others  —— 父进程是 GUI 本体（Catact.exe），说明另一个 Catact 正在用它，不能动。
    """
    by_pid = {r["pid"]: r for r in rows}
    orphans, others = [], []
    for r in rows:
        if r["name"].lower() not in ("python.exe", "pythonw.exe"):
            continue
        if "mx_bridge.py" not in r["cmd"]:
            continue
        m = re.search(r"--port\s+(\d+)", r["cmd"])
        if m and int(m.group(1)) != int(port):
            continue
        if self_pid and r["ppid"] == self_pid:
            continue                      # 自己的桥，交给 bridge.stop() 管
        parent = by_pid.get(r["ppid"])
        pname = parent["name"].lower() if parent else ""
        if parent is None or pname in _CONSOLE_PARENTS:
            orphans.append(r)
        else:
            others.append(r)
    return orphans, others


def find_bridge_procs(port, self_pid=0):
    """查一遍正在跑的 mx_bridge.py，返回 (orphans, others)。约 0.5–1 秒。"""
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        "Get-CimInstance Win32_Process | "
        "ForEach-Object { \"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.Name)`t$($_.ExecutablePath)`t$($_.CommandLine)\" }"
    )
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=15, creationflags=_NO_WINDOW)
        return classify_bridge_procs(parse_proc_table(r.stdout), port, self_pid)
    except Exception:
        return [], []


def button_states(running, starting=False):
    """工具栏三个按钮的唯一状态来源（纯函数，方便离线测试）。

    规则：
      · 桥在运行   → 启动禁用、停止可点、刷新可点
      · 正在启动中 → 三个都禁用（避免重复拉起第二个桥）
      · 桥未运行   → 启动可点、停止禁用、刷新禁用

    1.0.3 的旧实现把「按钮当前状态」也当成判断条件（btn_start["state"] !=
    "normal" 就继续禁用），结果点过一次启动后，即便桥已停止，启动键也永远
    回不到 normal —— 只能从「工具 → 启动桥」菜单绕过去。这里彻底改成只依赖
    进程事实，不再读按钮自身状态。
    """
    on, off = "normal", "disabled"
    if running:
        return {"start": off, "stop": on, "refresh": on}
    if starting:
        return {"start": off, "stop": off, "refresh": off}
    return {"start": on, "stop": off, "refresh": off}



BG = "#f0f0f0"          # Win7 经典系统灰（按钮/面板/画布同色）
BAR = "#f0f0f0"
BORDER = "#808080"      # 3D 斜面的深色边
PANEL = "#f0f0f0"
WHITE = "#ffffff"
TITLE_BG = "#d4d0c8"    # 经典工具条/表头灰
TITLE_ACTIVE = "#0a246a"  # 选中行深蓝
TITLE_FG = "#000000"
GRID_LINE = "#808080"
ONE_BG = "#008000"      # 纯绿（状态指示）
ONE_FG = "#ffffff"
ZERO_FG = "#000000"
ACCENT = "#000080"      # 经典深蓝，仅用于地址强调/选中
RED = "#c00000"         # 纯红（停止/故障）
GREEN = "#008000"       # 纯绿（正常/接通）
YELLOW = "#c8a000"      # 纯黄（等待/警告）

FONT = ("Segoe UI", 9)
FONT_B = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 10)
MONO = ("Segoe UI", 9)


# ---------------------------------------------------------------- 地址映射

class AddrMap:
    BIT = {
        "0x": [
            (1, 8000, "M"), (8001, 9000, "S"), (9001, 10000, "B"),
            (10001, 11000, "X"), (11001, 12000, "Y"), (12001, 13000, "T"),
            (13001, 14000, "C"), (14001, 15000, "L"), (15001, 16000, "SM"),
            (16001, 17000, "F"), (17001, 18000, "ST"), (18001, 19000, "SB"),
        ],
        "1x": [
            (1, 1000, "X"), (1001, 2000, "Y"), (2001, 3000, "T"),
            (3001, 4000, "C"), (4001, 5000, "L"), (5001, 6000, "SM"),
            (6001, 7000, "F"), (7001, 8000, "ST"), (8001, 9000, "SB"),
        ],
    }
    WORD = {
        "4x": [
            (1, 8000, "D"), (8001, 9000, "W"), (9001, 10000, "T"),
            (10001, 11000, "C"), (11001, 12000, "ST"), (12001, 13000, "SD"),
            (13001, 21000, "ZR"), (21001, 21020, "Z"), (22001, 30000, "R"),
            (30001, 31000, "SW"),
        ],
    }

    OCTAL = {"X", "Y"}
    HEX = {"W", "B", "SB", "SW"}
    TWO = ("SM", "SD", "SB", "SW", "ST", "ZR")

    # (按钮, 区域, 设备, 起始, 默认点数)
    # X/Y 直接用 0x 可写镜像：一个元件一个地址，按钮和指示灯都用它（方案 B）
    BAR = [
        ("M", "0x", "M", 0, 400), ("X", "0x", "X", 0, 200), ("Y", "0x", "Y", 0, 200),
        ("D", "4x", "D", 0, 400), ("W", "4x", "W", 0, 200), ("T", "1x", "T", 0, 200),
        ("C", "1x", "C", 0, 200), ("L", "1x", "L", 0, 200), ("S", "0x", "S", 0, 200),
        ("B", "0x", "B", 0, 200), ("SM", "1x", "SM", 0, 200), ("F", "1x", "F", 0, 200),
        ("ST", "1x", "ST", 0, 200), ("SB", "1x", "SB", 0, 200), ("SD", "4x", "SD", 0, 200),
        ("Z", "4x", "Z", 0, 20), ("R", "4x", "R", 0, 200), ("SW", "4x", "SW", 0, 200),
    ]

    @classmethod
    def radix(cls, dev):
        if dev in cls.OCTAL:
            return 8
        if dev in cls.HEX:
            return 16
        return 10

    @classmethod
    def fmt(cls, dev, n):
        r = cls.radix(dev)
        return format(n, "o") if r == 8 else (format(n, "X") if r == 16 else str(n))

    @classmethod
    def segment(cls, area, dev):
        table = cls.BIT.get(area) or cls.WORD.get(area) or []
        for start, end, d in table:
            if d == dev:
                return start, end
        return None

    @classmethod
    def name_to_addr(cls, text):
        s = text.strip().upper().replace(" ", "")
        if not s:
            return None, "输入为空"
        is_val = s.endswith(".V")
        if is_val:
            s = s[:-2]
        m = re.match(r"^([A-Z]{1,2})([0-9A-F]+)$", s)
        if not m:
            return None, "格式应为 M0 / Y10 / D100 / T5.V"
        letters = m.group(1)
        dev = letters if letters in cls.TWO else letters[:1]
        rest = s[len(dev):]
        r = cls.radix(dev)
        try:
            value = int(rest, r)
        except ValueError:
            return None, f"{dev} 是 {8 if r == 8 else 16} 进制，'{rest}' 不合法"

        areas = ["4x"] if is_val else (["1x", "4x"] if dev in ("T", "C", "ST") else ["1x", "0x", "4x"])
        if dev in ("X", "Y") and not is_val:
            # 方案 B：X/Y 统一用 0x 可写镜像（x0 → 0x 10001），按钮和灯同一个地址
            areas = ["0x", "1x"]
        for area in areas:
            seg = cls.segment(area, dev)
            if not seg:
                continue
            start, end = seg
            if 0 <= value <= end - start:
                return (area, start + value), None
        return None, f"超出范围：{text}"

    @classmethod
    def mirror_addr(cls, area, addr):
        """1x 只读地址对应的 0x 可写镜像（规则：0x = 1x + 10000）。无镜像返回 None。"""
        if area != "1x":
            return None
        for start, end, dev in cls.BIT["1x"]:
            if start <= addr <= end:
                m = addr + 10000
                for s2, e2, d2 in cls.BIT["0x"]:
                    if s2 <= m <= e2 and d2 == dev:
                        return m
        return None

    @classmethod
    def addr_to_name(cls, area, addr):
        area = area.lower().replace(" ", "")
        table = cls.BIT.get(area) or cls.WORD.get(area)
        if not table:
            return None, "区域应为 0x / 1x / 4x"
        if addr < 1:
            return None, "地址从 1 开始"
        for start, end, dev in table:
            if start <= addr <= end:
                idx = addr - start
                suffix = ".V" if area == "4x" and dev in ("T", "C", "ST") else ""
                return f"{dev}{cls.fmt(dev, idx)}{suffix}", None
        return None, f"{area} 区没有地址 {addr}"

    @classmethod
    def parse_addr_text(cls, text):
        s = text.strip().lower().replace(" ", "")
        m = re.match(r"^(0x|1x|4x)[:\-]?(\d+)$", s)
        if not m:
            return None, "格式应为 0x1 / 1x1002 / 4x101"
        return (m.group(1), int(m.group(2))), None


# ---------------------------------------------------------------- Modbus

class MbClient:
    """持久连接的 Modbus 客户端：断线自动重连，不再每个请求都新建 TCP，
    避免桥那边「连接/断开」日志刷屏。"""

    def __init__(self, host, port, timeout=1.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._tid = 0
        self.sock = None

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _connect(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)

    def _req(self, pdu):
        err = None
        for attempt in range(2):          # 第一次失败：重连再试一次
            if self.sock is None:
                self._connect()
            try:
                self._tid = (self._tid + 1) & 0xFFFF
                self.sock.sendall(struct.pack(">HHHB", self._tid, 0, len(pdu) + 1, 1) + pdu)
                head = b""
                while len(head) < 7:
                    chunk = self.sock.recv(7 - len(head))
                    if not chunk:
                        raise OSError("连接被关闭")
                    head += chunk
                tid, pid, length, unit = struct.unpack(">HHHB", head)
                body = b""
                while len(body) < length - 1:
                    chunk = self.sock.recv(length - 1 - len(body))
                    if not chunk:
                        raise OSError("响应不完整")
                    body += chunk
                if body[0] & 0x80:
                    raise OSError(f"Modbus 异常码 0x{body[1]:02X}")
                return body
            except OSError as e:
                err = e
                self.close()
        raise err

    def read_bits(self, fc, addr, qty):
        body = self._req(struct.pack(">BHH", fc, addr, qty))
        bits = []
        for i in range(qty):
            byte = body[2 + i // 8] if 2 + i // 8 < len(body) else 0
            bits.append((byte >> (i % 8)) & 1)
        return bits

    def read_words(self, addr, qty):
        body = self._req(struct.pack(">BHH", 3, addr, qty))
        return list(struct.unpack(">" + "H" * qty, body[2:2 + qty * 2]))

    def write_coil(self, addr, on):
        self._req(struct.pack(">BHH", 5, addr, 0xFF00 if on else 0x0000))

    def write_word(self, addr, val):
        self._req(struct.pack(">BHH", 6, addr, val & 0xFFFF))


# ---------------------------------------------------------------- 桥进程

class BridgeProc:
    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.q = queue.Queue()

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self):
        if self.running:
            return False, "桥已经在运行"
        py = self.cfg["python32"]
        if not os.path.exists(py):
            return False, f"找不到 32 位 Python：\n{py}"
        if not os.path.exists(BRIDGE_SCRIPT):
            return False, f"找不到桥脚本：\n{BRIDGE_SCRIPT}"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.proc = subprocess.Popen(
                [py, "-u", BRIDGE_SCRIPT, "--station", str(self.cfg["station"]),
                 "--port", str(self.cfg["port"]), "--parent-pid", str(os.getpid())],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                creationflags=flags,
            )
        except Exception as e:
            return False, f"启动失败：{e}"
        threading.Thread(target=self._reader, daemon=True).start()
        return True, "桥已启动"

    def _reader(self):
        for line in self.proc.stdout:
            self.q.put(line.rstrip())
        self.q.put("__EXIT__")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(3)
            except Exception:
                self.proc.kill()
        if self.proc is not None:
            try:
                if self.proc.stdout:
                    self.proc.stdout.close()
            except Exception:
                pass
        self.proc = None

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.q.get_nowait())
            except queue.Empty:
                break
        return out


# ---------------------------------------------------------------- 浮动子窗口（原生窗口）

class FloatWindow:
    """真正的 Toplevel：原生标题栏、原生拖拽与缩放，拖动时由系统跟随鼠标，无残影。"""

    seq = 0

    def __init__(self, app, title, w, h, x=None, y=None, resizable=True):
        FloatWindow.seq += 1
        self.app = app
        self.win = tk.Toplevel(app)
        self.outer = self.win                      # 兼容既有调用
        self.win.title(title)
        self.win.configure(bg=WHITE)
        self.win.transient(app)                    # 始终浮在主窗口之上
        self.win.resizable(resizable, resizable)

        if x is None:
            x = 16 + ((FloatWindow.seq - 1) % 6) * 28
        if y is None:
            y = 118 + ((FloatWindow.seq - 1) % 6) * 24
        # 高 DPI 下字体按磅值放大了，窗口的像素尺寸和坐标也要同比例放大，
        # 保持和 100% 缩放时一致的观感
        w, h = int(w * S), int(h * S)
        x, y = int(x * S), int(y * S)
        px, py = self._clamp(app, x, y, w, h)
        self.win.geometry("%dx%d+%d+%d" % (w, h, px, py))

        # 追踪子窗口在屏幕上的绝对位置：父窗口跟随逻辑直接读它，
        # 不再每次都查 winfo_x/winfo_y（那会同步穿透 Tcl 层，拖动时很卡）。
        self._target = [px, py]

        def _track_self(e):
            if e.widget is self.win:
                try:
                    self._target[0] = self.win.winfo_x()
                    self._target[1] = self.win.winfo_y()
                except tk.TclError:
                    pass
        self.win.bind("<Configure>", _track_self, add="+")

        self.alive = True
        self.body = tk.Frame(self.win, bg=WHITE)
        self.body.pack(fill="both", expand=True)

        # DWM 属性要在窗口映射之后再设，否则会被系统主题覆盖
        self.win.after(120, lambda: light_titlebar(self.win))
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Button-1>", lambda e: self.lift(), add="+")

    @staticmethod
    def _clamp(app, x, y, w, h):
        sw, sh = app.winfo_screenwidth(), app.winfo_screenheight()
        bx, by = app.winfo_rootx(), app.winfo_rooty()
        px = max(0, min(bx + x, sw - w - 10))
        py = max(0, min(by + y, sh - h - 60))
        return px, py

    def lift(self):
        try:
            self.win.lift()
        except tk.TclError:
            pass

    def set_title(self, text):
        try:
            self.win.title(text)
        except tk.TclError:
            pass

    def close(self):
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.app.on_window_closed(self)


class MonitorWindow(FloatWindow):
    COLS = 10
    CELL_W = 54
    CELL_H = 22

    def __init__(self, app, dev, area, start, count, x=None, y=None):
        self.dev = dev
        self.area = area
        self.start = start
        self.count = count
        self.is_bit = area in ("0x", "1x")
        self.cells = []
        self._last = [None] * count
        self._state = None
        seg = AddrMap.segment(area, dev)
        self.base = seg[0] + start - 1

        rows = (count + self.COLS - 1) // self.COLS
        w = self.COLS * self.CELL_W + 26
        h = min(rows, 16) * self.CELL_H + 6
        title = T("monitor_title", dev=dev,
                  start=AddrMap.fmt(dev, start),
                  end=AddrMap.fmt(dev, start + count - 1), count=count)
        super().__init__(app, title, w, h, x=x, y=y)
        self.win.minsize(self.COLS * 26 + 26, 120)

        wrap = tk.Frame(self.body, bg=WHITE)
        wrap.pack(fill="both", expand=True)
        inner = tk.Canvas(wrap, bg=WHITE, highlightthickness=0)
        sb = tk.Scrollbar(wrap, orient="vertical", command=inner.yview)
        inner.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        inner.pack(side="left", fill="both", expand=True)

        grid = tk.Frame(inner, bg=GRID_LINE)
        for _c in range(self.COLS):
            grid.grid_columnconfigure(_c, weight=1, uniform="cell")
        wid = inner.create_window((0, 0), window=grid, anchor="nw")

        for i in range(count):
            num = start + i
            name = f"{dev}{AddrMap.fmt(dev, num)}"
            cell = tk.Label(grid, text="--", font=MONO, width=6, height=1,
                            bg=WHITE, fg=ZERO_FG, bd=1, relief="sunken",
                            padx=1, pady=3)
            cell.grid(row=i // self.COLS, column=i % self.COLS, padx=(0, 1), pady=(0, 1), sticky="nsew")
            cell.bind("<Button-1>", lambda e, n=name: app.copy_text(f"{n} = {self._addr(n)}"))
            cell.bind("<Button-3>", lambda e, k=i: self._menu(e, k))
            cell.bind("<Enter>", lambda e, n=name: app.set_hint(f"{n} = {self._addr(n)}"))
            cell.bind("<Leave>", lambda e: app.set_hint(""))
            self.cells.append(cell)

        def _sync(_=None):
            grid.update_idletasks()
            inner.configure(scrollregion=(0, 0, max(inner.winfo_width(), grid.winfo_reqwidth()),
                                          max(inner.winfo_height(), grid.winfo_reqheight())))
            inner.itemconfigure(wid, width=max(inner.winfo_width(), grid.winfo_reqwidth()))
        inner.bind("<Configure>", _sync)
        _sync()
        inner.bind("<MouseWheel>", lambda e: inner.yview_scroll(int(-e.delta / 120), "units"))

    def _addr(self, name):
        res, err = AddrMap.name_to_addr(name)
        return f"{res[0]} {res[1]}" if not err else "?"

    def _menu(self, event, idx):
        name = f"{self.dev}{AddrMap.fmt(self.dev, self.start + idx)}"
        m = tk.Menu(self.outer, tearoff=0, font=FONT)
        if self.area == "0x":
            m.add_command(label=f"{name} 置 1", command=lambda: self._write_bit(idx, 1))
            m.add_command(label=f"{name} 置 0", command=lambda: self._write_bit(idx, 0))
        elif self.area == "4x":
            m.add_command(label=f"写入 {name}…", command=lambda: self._write_word(idx))
        else:
            m.add_command(label=f"{name}（只读）", state="disabled")
        m.tk_popup(event.x_root, event.y_root)

    def _write_bit(self, idx, v):
        c = MbClient(self.app.cfg["host"], self.app.cfg["port"])
        try:
            c.write_coil(self.base + idx, v)
            self.app.log(f"写入 {self.dev}{AddrMap.fmt(self.dev, self.start + idx)} = {v}")
        except Exception as e:
            self.app.log(f"写入失败：{e}")
        finally:
            c.close()

    def _write_word(self, idx):
        from tkinter import simpledialog
        name = f"{self.dev}{AddrMap.fmt(self.dev, self.start + idx)}"
        val = simpledialog.askinteger("写入", f"{name} 的值（0–65535）",
                                      parent=self.app, minvalue=0, maxvalue=65535)
        if val is None:
            return
        c = MbClient(self.app.cfg["host"], self.app.cfg["port"])
        try:
            c.write_word(self.base + idx, val)
            self.app.log(f"写入 {name} = {val}")
        except Exception as e:
            self.app.log(f"写入失败：{e}")
        finally:
            c.close()

    def apply(self, values):
        self._state = "ok"
        for i, (cell, v) in enumerate(zip(self.cells, values)):
            if self.is_bit:
                v = 1 if v else 0
                if self._last[i] == v:
                    continue
                self._last[i] = v
                if v:
                    cell.config(text="1", bg=ONE_BG, fg=ONE_FG)
                else:
                    cell.config(text="0", bg=WHITE, fg=ZERO_FG)
            else:
                if self._last[i] == v:
                    continue
                self._last[i] = v
                cell.config(text=str(v), bg=WHITE, fg="#1f1f1f")

    def apply_error(self):
        if self._state == "err":
            return
        self._state = "err"
        for i, cell in enumerate(self.cells):
            self._last[i] = None
            cell.config(text="--", bg=WHITE, fg=ZERO_FG)
        if self.cells:
            self.cells[0].config(text="×", bg=RED, fg="#ffffff")

    def apply_neutral(self):
        if self._state == "neutral":
            return
        self._state = "neutral"
        for i, cell in enumerate(self.cells):
            self._last[i] = None
            cell.config(text="--", bg=WHITE, fg=ZERO_FG)


class ConvertWindow(FloatWindow):
    def __init__(self, app):
        super().__init__(app, "地址换算", 470, 158, x=16, y=458, resizable=False)
        body = self.body
        body.configure(bg=PANEL)

        tk.Label(body, text="PLC 元件名", font=FONT_B, bg=PANEL).grid(row=0, column=0, padx=10, pady=(10, 2))
        tk.Label(body, text="EBPro 地址", font=FONT_B, bg=PANEL).grid(row=0, column=2, padx=10, pady=(10, 2))
        tk.Label(body, text="", width=4, bg=PANEL).grid(row=0, column=1)

        self.e_name = tk.Entry(body, font=FONT_TITLE, width=13, justify="center",
                               relief="sunken", bd=2, bg=WHITE, fg="#000000")
        self.e_name.grid(row=1, column=0, padx=8, pady=4, ipady=4)
        tk.Label(body, text="⇄", font=("Segoe UI", 12), bg=PANEL, fg="#000000").grid(row=1, column=1)
        self.e_addr = tk.Entry(body, font=FONT_TITLE, width=13, justify="center",
                               relief="sunken", bd=2, bg=WHITE, fg="#000000")
        self.e_addr.grid(row=1, column=2, padx=8, pady=4, ipady=4)

        self.e_name.bind("<KeyRelease>", lambda e: self.on_name())
        self.e_addr.bind("<KeyRelease>", lambda e: self.on_addr())

        self.lbl = tk.Label(body, text="在任一侧输入，另一侧自动补全", font=FONT,
                            bg=PANEL, fg="#000000")
        self.lbl.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(2, 4))

        ex = tk.Frame(body, bg=PANEL)
        ex.grid(row=3, column=0, columnspan=3, sticky="w", padx=8)
        for t in ("M0", "Y1", "S0", "T5.V", "1x1002", "0x8001"):
            tk.Button(ex, text=t, font=FONT, bg=BAR, fg="#000000", relief="raised",
                      bd=2, padx=3,
                      command=lambda x=t: self.example(x)).pack(side="left", padx=2)

        tk.Label(body, text="（各区起始地址见主窗口「Address Reference」）", font=FONT,
                 bg=PANEL, fg="#404040").grid(row=4, column=0, columnspan=3, sticky="w",
                                              padx=12, pady=(2, 6))

    def example(self, text):
        if text.lower().startswith(("0x", "1x", "4x")):
            self.e_addr.delete(0, "end")
            self.e_addr.insert(0, text)
            self.on_addr()
        else:
            self.e_name.delete(0, "end")
            self.e_name.insert(0, text)
            self.on_name()

    def on_name(self):
        text = self.e_name.get().strip()
        if not text:
            self.e_addr.delete(0, "end")
            return
        res, err = AddrMap.name_to_addr(text)
        self.e_addr.delete(0, "end")
        if err:
            self.lbl.config(text=err, fg=RED)
        else:
            self.e_addr.insert(0, f"{res[0]} {res[1]}")
            if res[0] == "0x":
                tip = "　（可读可写，按钮/开关/指示灯都用它）"
            elif res[0] == "1x":
                hint = AddrMap.mirror_addr(*res)
                tip = f"　（只读；按钮/开关请用 0x {hint}）" if hint else "　（只读）"
            else:
                tip = "　（可读可写）"
            self.lbl.config(text=f"{text.upper()}  →  {res[0]} {res[1]}{tip}", fg=GREEN)

    def on_addr(self):
        text = self.e_addr.get().strip()
        if not text:
            self.e_name.delete(0, "end")
            return
        parsed, err = AddrMap.parse_addr_text(text)
        self.e_name.delete(0, "end")
        if err:
            self.lbl.config(text=err, fg=RED)
            return
        area, addr = parsed
        name, err2 = AddrMap.addr_to_name(area, addr)
        if err2:
            self.lbl.config(text=err2, fg=RED)
        else:
            self.e_name.insert(0, name)
            self.lbl.config(text=f"{area} {addr}  →  {name}", fg=GREEN)


# ---------------------------------------------------------------- 主界面

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = self.load_cfg()
        global LANG
        LANG = "zh" if str(self.cfg.get("lang", "zh")).lower().startswith("zh") else "en"
        self._apply_fonts()
        self.lang_var = tk.StringVar(value=LANG)
        self.title(T("app_title", ver=APP_VERSION))
        if os.path.exists(ICON_PATH):
            try:
                # default=True：主窗口、所有子窗口和任务栏统一使用该图标
                self.iconbitmap(default=ICON_PATH)
            except Exception:
                pass
        # 磅值字体按实际 DPI 渲染（96/72≈1.33 基准 × DPI/96）
        self.tk.call("tk", "scaling", DPI / 72.0)
        self.geometry("%dx%d" % (int(1280 * S), int(820 * S)))
        self.minsize(int(1040 * S), int(680 * S))
        self.configure(bg=BG)
        self._init_style()
        self.after(60, lambda: light_titlebar(self))

        self.bridge = BridgeProc(self.cfg)
        self.windows = {}
        self.convert_win = None
        self.result_q = queue.Queue()
        self.polling = True
        self.link_ok = False
        self.port_ok = False
        # 桥上报的、经过回读验证的 MX 会话状态：
        #   True=已连；False=未连；None=还没收到桥的回报（启动中/正在重连）
        self.mx_up = None
        # 启动桥的动作正在进行（Popen 前后的一小段），防止双击拉起两个桥
        self._starting = False
        # 刷新按钮的短暂忙状态：发出重连请求后禁用约 2 秒，避免连点刷屏
        self._refresh_busy_until = 0.0
        self._refresh_seq = 0
        self._state_ver = 0
        # GX 仿真进程检测（后台线程写，主线程只读）
        self._sim_running = None
        # 自动重连兜底：桥一直没连上时，GUI 每 5 秒补发一次刷新请求（每轮只补一次）
        self._link_wait_since = None
        self._link_backup_sent = False
        # 状态栏报警计数（写入失败 / 未生效 / 拒绝时累加，清日志时归零）
        self._alarm_count = 0
        # ActComm.exe 自动定位缓存（None=还没找过，""=找过但没找到）
        self._mx_util_cache = None

        self._build_menu()
        self._build_toolbar()
        self._build_body()
        self._build_status()

        self._last_pos = (self.winfo_rootx(), self.winfo_rooty())
        self._move_pending = False
        self.bind("<Configure>", self._on_parent_move, add="+")
        self._refresh_buttons()

        threading.Thread(target=self._poll_loop, daemon=True).start()
        threading.Thread(target=self._probe_loop, daemon=True).start()
        self.after(200, self._tick)

    # ---------- 界面字体（中文优先用雅黑，英文保持 Segoe UI）
    def _apply_fonts(self):
        global FONT, FONT_B, FONT_TITLE, MONO, UI_FONT_FAMILY
        if LANG == "zh":
            try:
                families = set(tkfont.families(self))
            except tk.TclError:
                families = set()
            UI_FONT_FAMILY = "Segoe UI"
            for cand in ("Microsoft YaHei UI", "Microsoft YaHei",
                         "SimSun", "Segoe UI"):
                if cand in families:
                    UI_FONT_FAMILY = cand
                    break
        else:
            UI_FONT_FAMILY = "Segoe UI"
        FONT = (UI_FONT_FAMILY, 9)
        FONT_B = (UI_FONT_FAMILY, 9, "bold")
        FONT_TITLE = (UI_FONT_FAMILY, 10)
        MONO = (UI_FONT_FAMILY, 9)

    # ---------- 配置
    def load_cfg(self):
        cfg = dict(DEFAULT_CFG)
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
        return cfg

    def save_cfg(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    # ---------- Win7 经典控件主题
    def _init_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("classic")       # 关闭 vista/现代主题，回到 3D 经典
        except tk.TclError:
            pass
        st.configure("Treeview", font=FONT, rowheight=int(20 * S),
                     background=BG, fieldbackground=BG, foreground="#000000",
                     borderwidth=1, relief="sunken")
        st.map("Treeview", background=[("selected", TITLE_ACTIVE)],
               foreground=[("selected", "#ffffff")])
        st.configure("Treeview.Heading", font=FONT_B, background=TITLE_BG,
                     foreground="#000000", relief="raised", borderwidth=1)
        st.configure("TCombobox", fieldbackground=WHITE, background=BAR, font=FONT)

    # ---------- 菜单（默认中文，Options → Language 可切英文）
    def _build_menu(self):
        m = tk.Menu(self, font=FONT)

        fm = tk.Menu(m, tearoff=0, font=FONT)
        fm.add_command(label=T("menu_start"), command=self.start_bridge)
        fm.add_command(label=T("menu_stop"), command=self.stop_bridge)
        fm.add_command(label=T("menu_refresh"), command=self.refresh_link)
        fm.add_separator()
        fm.add_command(label=T("menu_export"), command=self.export_all)
        fm.add_separator()
        fm.add_command(label=T("menu_exit"), command=self.on_close)
        m.add_cascade(label=T("menu_file"), menu=fm)

        em = tk.Menu(m, tearoff=0, font=FONT)
        em.add_command(label=T("menu_clear"), command=self.clear_log)
        em.add_command(label=T("menu_convert"), command=self.open_convert)
        em.add_separator()
        em.add_command(label=T("menu_close_all"), command=self.close_all)
        m.add_cascade(label=T("menu_edit"), menu=em)

        vm = tk.Menu(m, tearoff=0, font=FONT)
        devm = tk.Menu(vm, tearoff=0, font=FONT)
        for text, area, dev, start, cnt in AddrMap.BAR:
            devm.add_command(label=T("menu_dev_monitor", dev=dev),
                             command=lambda d=dev: self.toggle_window(d))
        vm.add_cascade(label=T("menu_device_monitor"), menu=devm)
        vm.add_separator()
        vm.add_command(label=T("menu_show_log"), command=self._focus_log)
        vm.add_command(label=T("menu_show_addr"), command=self._focus_addr)
        m.add_cascade(label=T("menu_view"), menu=vm)

        om = tk.Menu(m, tearoff=0, font=FONT)
        om.add_command(label=T("menu_bridge_settings"), command=self.bridge_settings)
        om.add_command(label=T("menu_mx_check"), command=self.mx_env_check)
        om.add_command(label=T("menu_station_tool"), command=self.open_mx_utility)
        om.add_separator()
        lm = tk.Menu(om, tearoff=0, font=FONT)
        lm.add_radiobutton(label="中文", variable=self.lang_var, value="zh",
                           command=lambda: self.change_language("zh"))
        lm.add_radiobutton(label="English", variable=self.lang_var, value="en",
                           command=lambda: self.change_language("en"))
        om.add_cascade(label=T("menu_language"), menu=lm)
        m.add_cascade(label=T("menu_options"), menu=om)

        hm = tk.Menu(m, tearoff=0, font=FONT)
        hm.add_command(label=T("menu_usage"), command=self.show_help)
        hm.add_command(label=T("menu_about"), command=self.show_about)
        m.add_cascade(label=T("menu_help"), menu=hm)
        self.config(menu=m)

    def change_language(self, lang):
        if lang == LANG:
            return
        if lang == "zh":
            msg = ("语言已切换为中文。\n\n"
                   "需要重启 Catact 才能完整生效（会先停止当前桥），是否现在重启？")
        else:
            msg = ("Language switched to English.\n\n"
                   "Catact must restart to apply (the bridge will stop). Restart now?")
        if not messagebox.askyesno(T("lang_restart_title"), msg):
            self.lang_var.set(LANG)
            return
        self.cfg["lang"] = lang
        if not self.save_cfg():
            self.cfg["lang"] = LANG
            self.lang_var.set(LANG)
            messagebox.showerror(T("lang_restart_title"), T("lang_save_fail"))
            return
        self.restart_app()

    def restart_app(self):
        """保存语言后重启自身（免安装 onefile / 源码运行都适用）。"""
        self.polling = False
        try:
            self.bridge.stop()
        except Exception:
            pass
        try:
            if getattr(sys, "frozen", False):
                subprocess.Popen([sys.executable], cwd=APP_DIR,
                                 creationflags=_NO_WINDOW)
            else:
                subprocess.Popen([sys.executable, os.path.abspath(__file__)],
                                 cwd=APP_DIR)
        except Exception:
            messagebox.showerror(T("lang_restart_title"), T("lang_restart_fail"))
            return
        self.destroy()

    # ---------- 工具栏（凸起斜面图标按钮，按下凹陷）
    def _build_toolbar(self):
        bar = tk.Frame(self, bg=BAR, bd=1, relief="raised")
        bar.pack(side="top", fill="x")

        def tb(text, cmd, width, bg=BAR, fg="#000000"):
            b = tk.Button(bar, text=text, command=cmd, font=FONT, bg=bg, fg=fg,
                          relief="raised", bd=2, width=width, padx=2, pady=1,
                          disabledforeground="#808080", cursor="hand2")
            b.pack(side="left", padx=(3, 0), pady=2)
            return b

        self.btn_new = tb(T("tb_new"), self.clear_log, 6)
        self.btn_open = tb(T("tb_open"), self.open_convert, 7)
        self.btn_save = tb(T("tb_save"), self.export_all, 6)
        tk.Frame(bar, bg=BORDER, width=2).pack(side="left", fill="y", padx=6, pady=4)
        self.btn_start = tb(T("tb_run"), self.start_bridge, 7, GREEN, "#ffffff")
        self.btn_stop = tb(T("tb_stop"), self.stop_bridge, 7, RED, "#ffffff")
        self.btn_refresh = tb(T("tb_reset"), self.refresh_link, 7)

        # 右侧状态区：桥 LED + 端口/站号 + 仿真 LED
        right = tk.Frame(bar, bg=BAR)
        right.pack(side="right", padx=(0, 6), pady=2)

        self.led_canvas = tk.Canvas(right, width=12, height=12, bg=BAR,
                                    bd=0, highlightthickness=0)
        self.led_id = self.led_canvas.create_oval(2, 2, 10, 10, fill="#b0b0b0",
                                                  outline="#404040")
        self.led_canvas.pack(side="left", padx=(0, 3))
        self.lbl_conn = tk.Label(right, text=T("not_started"), font=FONT, bg=BAR,
                                 fg="#000000", width=11, anchor="w")
        self.lbl_conn.pack(side="left")

        tk.Frame(right, bg=BORDER, width=1).pack(side="left", fill="y", padx=5, pady=4)
        tk.Label(right, text=T("port"), font=FONT, bg=BAR).pack(side="left")
        self.lbl_port = tk.Label(right, text=str(self.cfg["port"]), font=FONT,
                                 bg=WHITE, fg="#000000", relief="sunken", bd=1,
                                 width=5, anchor="center")
        self.lbl_port.pack(side="left", padx=(3, 0))
        tk.Label(right, text=T("station"), font=FONT, bg=BAR).pack(side="left", padx=(6, 0))
        self.lbl_st = tk.Label(right, text=str(self.cfg["station"]), font=FONT,
                               bg=WHITE, fg="#000000", relief="sunken", bd=1,
                               width=3, anchor="center")
        self.lbl_st.pack(side="left", padx=(3, 0))

        tk.Frame(right, bg=BORDER, width=1).pack(side="left", fill="y", padx=5, pady=4)
        tk.Label(right, text=T("sim"), font=FONT, bg=BAR).pack(side="left")
        self.sim_canvas = tk.Canvas(right, width=12, height=12, bg=BAR,
                                    bd=0, highlightthickness=0)
        self.sim_id = self.sim_canvas.create_oval(2, 2, 10, 10, fill="#b0b0b0",
                                                  outline="#404040")
        self.sim_canvas.pack(side="left", padx=(4, 3))
        self.lbl_sim = tk.Label(right, text=T("detecting"), font=FONT, bg=BAR,
                                fg="#000000", width=7, anchor="w")
        self.lbl_sim.pack(side="left")

    def _set_led(self, color):
        try:
            self.led_canvas.itemconfigure(self.led_id, fill=color)
        except Exception:
            pass

    def _set_sim_led(self, color):
        try:
            self.sim_canvas.itemconfigure(self.sim_id, fill=color)
        except Exception:
            pass

    # ---------- 主体：左工程树 + 右监控画布
    def _build_body(self):
        body = tk.Frame(self, bg=BG, bd=1, relief="sunken")
        body.pack(side="top", fill="both", expand=True, padx=3, pady=(3, 0))

        hs = tk.PanedWindow(body, orient="horizontal", sashwidth=5, bg=BG,
                            bd=0, sashrelief="raised")
        hs.pack(fill="both", expand=True)
        self.hp = hs

        left = tk.Frame(hs, bg=BG)
        tk.Label(left, text=T("project"), font=FONT_B, bg=BG, fg="#000000",
                 anchor="w", relief="raised", bd=1).pack(fill="x")
        treewrap = tk.Frame(left, bg=BG, bd=1, relief="sunken")
        treewrap.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(treewrap, show="tree", selectmode="browse")
        tsb = tk.Scrollbar(treewrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        hs.add(left, minsize=int(190 * S), width=int(220 * S), stretch="never")

        right = tk.Frame(hs, bg=BG)
        hs.add(right, minsize=int(620 * S), stretch="always")
        self._build_mx_group(right)
        self._build_devbar(right)
        self._build_output_bar(right)
        self._build_workarea(right)
        self._fill_tree()
        self.after(180, self._update_mx_state)

    def _fill_tree(self):
        t = self.tree
        self._tree_map = {}
        root = t.insert("", "end", text=T("tree_root"), open=True)

        def node(parent, text, key=None, open=False):
            iid = t.insert(parent, "end", text=text, open=open)
            if key:
                self._tree_map[iid] = key
            return iid

        b = node(root, T("tree_bridge"), open=True)
        node(b, T("tree_control"), ("bridge", "control"))
        node(b, T("tree_sim"), ("bridge", "sim"))
        node(b, T("tree_settings"), ("bridge", "settings"))

        d = node(root, T("tree_devices"), open=True)
        for text, area, dev, start, cnt in AddrMap.BAR:
            node(d, f"{text}   ({area})", ("dev", dev))

        g = node(root, T("tree_diag"), open=True)
        node(g, T("tree_write_log"), ("diag", "log"))
        node(g, T("tree_addr_map"), ("diag", "addr"))

        h = node(root, T("tree_help"), open=True)
        node(h, T("tree_usage"), ("help", "usage"))
        node(h, T("tree_about"), ("help", "about"))

        t.bind("<<TreeviewSelect>>", self._on_tree_select)
        t.bind("<Double-1>", self._on_tree_double)

    def _tree_key(self):
        sel = self.tree.selection()
        return self._tree_map.get(sel[0]) if sel else None

    def _on_tree_select(self, _e=None):
        key = self._tree_key()
        if not key:
            return
        if key[0] == "dev":
            self.set_hint(T("hint_dev", dev=key[1]))
        elif key[1] == "log":
            self.set_hint(T("hint_log"))
        elif key[1] == "addr":
            self.set_hint(T("hint_addr"))
        else:
            self.set_hint(T("hint_key", kind=key[0], val=key[1]))

    def _on_tree_double(self, _e=None):
        key = self._tree_key()
        if not key:
            return
        kind, val = key
        if kind == "dev":
            self.toggle_window(val)
        elif kind == "bridge" and val == "control":
            self._show_bridge_status()
        elif kind == "bridge" and val == "sim":
            self._show_sim_status()
        elif kind == "bridge" and val == "settings":
            self.bridge_settings()
        elif kind == "diag" and val == "log":
            self._focus_log()
        elif kind == "diag" and val == "addr":
            self._focus_addr()
        elif kind == "help" and val == "usage":
            self.show_help()
        elif kind == "help" and val == "about":
            self.show_about()

    def _focus_log(self):
        try:
            h = self.pw.winfo_height()
            self.pw.sash_place(0, 0, max(120, h - int(210 * S)))
        except tk.TclError:
            pass
        self.txt_log.focus_set()

    def _show_bridge_status(self):
        mx = (T("conn_connected") if self.mx_up is True
              else T("conn_waiting") if self.mx_up is False
              else T("conn_connecting"))
        messagebox.showinfo(
            T("bridge_status_title"),
            T("bridge_status_body",
              proc=T("proc_running") if self.bridge.running else T("proc_stopped"),
              addr=f"{self.cfg['host']}:{self.cfg['port']}",
              station=self.cfg["station"], mx=mx))

    def _show_sim_status(self):
        sim = (T("sim_running") if self._sim_running
               else T("sim_not_running") if self._sim_running is False
               else T("detecting"))
        messagebox.showinfo(
            T("sim_status_title"),
            T("sim_status_body", sim=sim))

    def _focus_addr(self):
        try:
            h = self.pw.winfo_height()
            self.pw.sash_place(0, 0, max(120, h - int(90 * S)))
        except tk.TclError:
            pass

    # ---------- MX Environment 分组框（自动定位 + 一键打开 ActComm.exe）
    def _build_mx_group(self, parent):
        grp = tk.LabelFrame(parent, text=T("mx_group"), font=FONT_TITLE, bg=BG,
                            fg="#000000", relief="groove", bd=1, labelanchor="nw")
        grp.pack(side="top", fill="x", padx=4, pady=(4, 2))

        row = tk.Frame(grp, bg=BG)
        row.pack(fill="x", padx=4, pady=(2, 0))
        self.mx_canvas = tk.Canvas(row, width=12, height=12, bg=BG,
                                   bd=0, highlightthickness=0)
        self.mx_led = self.mx_canvas.create_oval(2, 2, 10, 10, fill="#b0b0b0",
                                                 outline="#404040")
        self.mx_canvas.pack(side="left", padx=(0, 4))
        self.lbl_mx_state = tk.Label(row, text=T("detecting"), font=FONT_B, bg=BG,
                                     fg="#000000", width=24, anchor="w")
        self.lbl_mx_state.pack(side="left")
        self.lbl_mx_path = tk.Label(row, text="", font=FONT, bg=BG, fg="#000000",
                                    anchor="w", justify="left",
                                    wraplength=int(700 * S))
        self.lbl_mx_path.pack(side="left", fill="x", expand=True, padx=(6, 0))

        row2 = tk.Frame(grp, bg=BG)
        row2.pack(fill="x", padx=4, pady=(3, 4))
        self.btn_mx_open = tk.Button(row2, text=T("mx_open"),
                                     command=self.open_mx_utility, font=FONT,
                                     bg=BAR, fg="#000000", relief="raised", bd=2,
                                     width=14, padx=2, pady=1, cursor="hand2")
        self.btn_mx_open.pack(side="left")
        tk.Button(row2, text=T("mx_locate"), command=self.locate_mx_utility,
                  font=FONT, bg=BAR, fg="#000000", relief="raised", bd=2,
                  width=9, padx=2, pady=1, cursor="hand2").pack(side="left", padx=4)
        tk.Button(row2, text=T("mx_recheck"),
                  command=lambda: self._update_mx_state(force=True),
                  font=FONT, bg=BAR, fg="#000000", relief="raised", bd=2,
                  width=9, padx=2, pady=1, cursor="hand2").pack(side="left")

    def _set_mx_led(self, color):
        try:
            self.mx_canvas.itemconfigure(self.mx_led, fill=color)
        except Exception:
            pass

    def _update_mx_state(self, force=False):
        installed = self.mx_installed()
        path = self.mx_utility_path(force=force)
        if installed:
            self._set_mx_led(GREEN)
            self.lbl_mx_state.config(text=T("mx_installed"))
        else:
            self._set_mx_led(RED)
            self.lbl_mx_state.config(text=T("mx_missing"))
        if path:
            self.lbl_mx_path.config(text=path)
        else:
            self.lbl_mx_path.config(text=T("mx_notfound"))

    # ---------- Device Monitor 分组框
    def _build_devbar(self, parent):
        grp = tk.LabelFrame(parent, text=T("dev_group"), font=FONT_TITLE, bg=BG,
                            fg="#000000", relief="groove", bd=1, labelanchor="nw")
        grp.pack(side="top", fill="x", padx=4, pady=(4, 2))
        bar = tk.Frame(grp, bg=BG)
        bar.pack(fill="x", padx=4, pady=(2, 4))
        tk.Label(bar, text=T("dev_label"), font=FONT, bg=BG,
                 fg="#000000").pack(side="left", padx=(0, 4))

        self.dev_btns = {}
        for text, area, dev, start, cnt in AddrMap.BAR:
            b = tk.Button(bar, text=text, font=FONT, bg=BAR, fg="#000000",
                          relief="raised", bd=2, width=4, padx=0, pady=0,
                          cursor="hand2", command=lambda d=dev: self.toggle_window(d))
            b.pack(side="left", padx=1)
            self.dev_btns[dev] = b

        tk.Button(bar, text=T("addr_btn"), font=FONT, bg=BAR, fg="#000000",
                  relief="raised", bd=2, width=7, padx=1, pady=0,
                  command=self.open_convert).pack(side="left", padx=(8, 0))

    # ---------- Y 输出分组框
    def _build_output_bar(self, parent):
        grp = tk.LabelFrame(parent, text=T("y_group"), font=FONT_TITLE, bg=BG,
                            fg="#000000", relief="groove", bd=1, labelanchor="nw")
        grp.pack(side="top", fill="x", padx=4, pady=(0, 2))
        wrap = tk.Frame(grp, bg=BG)
        wrap.pack(fill="x", padx=4, pady=(2, 3))
        self.out_labels = []
        for i in range(18):
            lbl = tk.Label(wrap, text=f"Y{format(i, 'o')}", font=FONT,
                           bg=WHITE, fg="#000000", width=4, bd=1, relief="sunken", padx=1)
            lbl.pack(side="left", padx=1)
            self.out_labels.append(lbl)

    # ---------- 工作区（监视窗口 + 地址速查） + 写入日志
    def _build_workarea(self, parent):
        pw = tk.PanedWindow(parent, orient="vertical", sashwidth=6, bg=BG, bd=0,
                            sashrelief="raised")
        pw.pack(side="top", fill="both", expand=True, padx=4, pady=(0, 3))
        self.pw = pw

        work = tk.Frame(pw, bg=BG)

        g1 = tk.LabelFrame(work, text=T("win_group"), font=FONT_TITLE, bg=BG,
                           fg="#000000", relief="groove", bd=1, labelanchor="nw")
        g1.pack(fill="x", padx=2, pady=(2, 4))
        head = tk.Frame(g1, bg=BG)
        head.pack(fill="x", padx=4, pady=(2, 2))
        self.lbl_wins = tk.Label(head, text="", font=FONT, bg=BG, fg="#000000")
        self.lbl_wins.pack(side="left")
        tk.Label(head, text=T("win_hint"),
                 font=FONT, bg=BG, fg="#404040").pack(side="right")

        self.winbox = tk.Frame(g1, bg=BG)
        self.winbox.pack(fill="x", padx=4, pady=(0, 4))
        self._refresh_work()

        self.addr_group = tk.LabelFrame(work, text=T("addr_group"), font=FONT_TITLE,
                                        bg=BG, fg="#000000", relief="groove", bd=1,
                                        labelanchor="nw")
        self.addr_group.pack(fill="both", expand=True, padx=2, pady=(0, 2))
        ref = tk.Frame(self.addr_group, bg=BG)
        ref.pack(fill="both", expand=True, padx=6, pady=(2, 6))
        tk.Label(ref, text=T("addr_note1"),
                 font=FONT, bg=BG, fg="#000000").pack(anchor="w", pady=(0, 4))

        tbl = tk.Frame(ref, bg=BG)
        tbl.pack(anchor="w")
        entries = [(t, area, dev) for t, area, dev, _s, _c in AddrMap.BAR]
        per = (len(entries) + 2) // 3
        for g in range(3):
            for r in range(per):
                i = g * per + r
                if i >= len(entries):
                    break
                t, area, dev = entries[i]
                seg = AddrMap.segment(area, dev)
                base = g * 4
                tk.Label(tbl, text=t, font=FONT_B, bg=BG, fg="#000000",
                         width=3, anchor="e").grid(row=r, column=base, padx=(0, 3), pady=1)
                tk.Label(tbl, text=area, font=FONT, bg=BG, fg=ACCENT,
                         width=3, anchor="w").grid(row=r, column=base + 1, sticky="w")
                tk.Label(tbl, text=str(seg[0]) if seg else "-", font=FONT,
                         bg=BG, fg="#000000", width=6, anchor="w").grid(row=r, column=base + 2, sticky="w")
                tk.Frame(tbl, bg=BG, width=22).grid(row=r, column=base + 3)

        tk.Label(ref, text=T("addr_note2"),
                 font=FONT, bg=BG, fg="#000000").pack(anchor="w", pady=(6, 0))
        tk.Label(ref, text=T("addr_note3"),
                 font=FONT, bg=BG, fg=ACCENT).pack(anchor="w", pady=(2, 0))

        logf = tk.LabelFrame(pw, text=T("log_group"), font=FONT_TITLE, bg=BG,
                             fg="#000000", relief="groove", bd=1, labelanchor="nw")
        inner = tk.Frame(logf, bg=BG, bd=1, relief="sunken")
        inner.pack(fill="both", expand=True, padx=4, pady=(2, 4))
        self.txt_log = tk.Text(inner, height=7, font=MONO, bg=WHITE, fg="#000000",
                               bd=0, relief="flat", wrap="none",
                               insertbackground="#000000")
        sb = tk.Scrollbar(inner, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.txt_log.pack(side="left", fill="both", expand=True)

        pw.add(work, minsize=int(240 * S), stretch="always")
        pw.add(logf, minsize=int(90 * S), stretch="never")
        self.after(120, self._set_log_height)

    def _set_log_height(self, px=None):
        px = int(170 * S) if px is None else px
        try:
            h = self.pw.winfo_height()
            if h > px + 140:
                self.pw.sash_place(0, 0, h - px)
        except tk.TclError:
            pass

    def _refresh_work(self):
        for wdg in self.winbox.winfo_children():
            wdg.destroy()
        items = [(d, w) for d, w in self.windows.items() if w.outer.winfo_exists()]
        self.lbl_wins.config(text=T("wins_open", n=len(items)) if items
                             else T("no_wins"))

        if not items:
            tip = T("win_tip")
            tk.Label(self.winbox, text=tip, font=FONT, bg=BG,
                     fg="#404040", justify="left").pack(anchor="w", pady=10)
            return

        for dev, win in items:
            row = tk.Frame(self.winbox, bg=BG)
            row.pack(fill="x", pady=1)
            tk.Label(row, text="▸", font=FONT, bg=BG,
                     fg=ACCENT).pack(side="left", padx=(0, 6))
            tk.Label(row, text=win.win.title(), font=FONT,
                     bg=BG, fg="#000000").pack(side="left")
            tk.Button(row, text=T("close"), font=FONT, bg=BAR, fg="#000000",
                      relief="raised", bd=2, padx=4,
                      cursor="hand2", command=win.close).pack(side="right", padx=2)
            tk.Button(row, text=T("front"), font=FONT, bg=BAR, fg="#000000",
                      relief="raised", bd=2, padx=4,
                      cursor="hand2", command=win.lift).pack(side="right", padx=2)

    # ---------- 状态栏（通讯/地址/模式/报警/时间五格）
    def _build_status(self):
        bar = tk.Frame(self, bg=BAR, bd=1, relief="sunken")
        bar.pack(side="bottom", fill="x")
        self.lbl_hint = tk.Label(bar, text=T("ready"), bg=BAR, font=FONT,
                                 anchor="w", fg="#000000")
        self.lbl_hint.pack(side="left", fill="x", expand=True, padx=6)

        def cell(width, text):
            lbl = tk.Label(bar, text=text, bg=BAR, font=FONT, fg="#000000",
                           anchor="w", relief="sunken", bd=1, width=width, padx=4)
            lbl.pack(side="right", fill="y")
            return lbl

        self.lbl_st_time = cell(20, "")
        self.lbl_st_alarm = cell(11, T("status_alarms", n=0))
        self.lbl_st_mode = cell(21, T("status_mode"))
        self.lbl_st_addr = cell(25, "")
        self.lbl_st_bridge = cell(22, T("status_bridge_stopped"))

    # ---------- 主窗口移动时带着子窗口一起走（节流 + Win32 直移）
    def _on_parent_move(self, e):
        if e.widget is not self or self._move_pending:
            return
        # 拖动时 Configure 每个像素都来一次，这里只做一次 15ms 调度，
        # 把逐像素的子窗口移动合并成 ~60fps 的批处理，避免卡顿。
        self._move_pending = True
        self.after(15, self._move_children)

    def _move_children(self):
        self._move_pending = False
        try:
            if self.state() != "normal":
                return
            nx, ny = self.winfo_rootx(), self.winfo_rooty()
        except tk.TclError:
            return
        ox, oy = self._last_pos
        self._last_pos = (nx, ny)
        dx, dy = nx - ox, ny - oy
        if not dx and not dy:
            return
        group = list(self.windows.values())
        if self.convert_win:
            group.append(self.convert_win)
        for w in group:
            if not getattr(w, "alive", False):
                continue
            try:
                w._target[0] += dx
                w._target[1] += dy
                move_window_fast(w.outer, w._target[0], w._target[1])
            except tk.TclError:
                pass

    # ---------- 基础
    def log(self, msg):
        msg = str(msg)
        if any(k in msg for k in ("失败", "未生效", "拒绝", "✗")):
            self._alarm_count += 1
        self.txt_log.insert("end", time.strftime("[%H:%M:%S] ") + msg + "\n")
        self.txt_log.see("end")

    def clear_log(self):
        self.txt_log.delete("1.0", "end")
        self._alarm_count = 0
        self.log("日志已清空")

    def set_hint(self, text):
        self.lbl_hint.config(text=text or "Ready")

    def copy_text(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_hint(f"已复制：{text}")

    # ---------- 窗口
    def toggle_window(self, dev):
        if dev in self.windows and self.windows[dev].outer.winfo_exists():
            self.windows[dev].close()
            return
        _, area, dv, start, cnt = next(x for x in AddrMap.BAR if x[2] == dev)
        seg = AddrMap.segment(area, dv)
        cnt = min(cnt, seg[1] - seg[0] + 1 - start)
        pos = {"M": (8, 108), "Y": (584, 108)}.get(dv)
        w = MonitorWindow(self, dv, area, start, cnt, x=pos[0], y=pos[1]) if pos \
            else MonitorWindow(self, dv, area, start, cnt)
        self.windows[dv] = w
        self.dev_btns[dv].config(bg=ACCENT, fg="#ffffff", relief="sunken")
        self._refresh_work()

    def on_window_closed(self, win):
        dev = getattr(win, "dev", None)
        if dev and self.windows.get(dev) is win:
            del self.windows[dev]
            if dev in self.dev_btns:
                self.dev_btns[dev].config(bg=BAR, fg="#000000", relief="raised")
        self._refresh_work()

    def open_convert(self):
        if self.convert_win and self.convert_win.outer.winfo_exists():
            self.convert_win.lift()
            return
        self.convert_win = ConvertWindow(self)
        self.convert_win.lift()

    def close_all(self):
        for w in list(self.windows.values()):
            if w.outer.winfo_exists():
                w.close()
        self.windows.clear()
        for b in self.dev_btns.values():
            b.config(bg=BAR, fg="#000000", relief="raised")
        if self.convert_win and self.convert_win.outer.winfo_exists():
            self.convert_win.close()
        self.convert_win = None
        self._refresh_work()

    # ---------- 桥
    def _bridges_on_port(self):
        """返回 (可安全清理的残留, 属于另一个 Catact 的桥)。"""
        return find_bridge_procs(self.cfg["port"], os.getpid())

    def _kill_bridges(self, procs):
        killed = []
        for p in procs:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(p["pid"])],
                               capture_output=True, timeout=8, creationflags=_NO_WINDOW)
                killed.append(p["pid"])
            except Exception as e:
                self.log(f"[清理] 结束 PID {p['pid']} 失败：{e}")
        return killed

    def _wait_port_free(self, timeout=4.0):
        end = time.time() + timeout
        while time.time() < end:
            if not self.port_open():
                return True
            time.sleep(0.15)
        return not self.port_open()

    def start_bridge(self):
        if self.bridge.running:
            self.log("桥已经在运行")
            return
        if self._starting:
            return
        self._starting = True
        self._refresh_buttons()
        try:
            if self.port_open():
                self.config(cursor="watch")
                self.update_idletasks()
                try:
                    orphans, others = self._bridges_on_port()
                    if others:
                        messagebox.showerror(
                            T("menu_start"),
                            f"端口 {self.cfg['port']} 正被另一个 Catact 的桥占用（PID {others[0]['pid']}）。\n\n"
                            "请先关掉那个 Catact 窗口（任务栏里可能有第二个图标），再启动。")
                        return
                    if orphans:
                        pids = self._kill_bridges(orphans)
                        self.log(f"[清理] 结束上次残留的桥进程 PID {', '.join(map(str, pids))}")
                        self._wait_port_free()
                    if self.port_open():
                        messagebox.showerror(
                            T("menu_start"),
                            f"端口 {self.cfg['port']} 被其他程序占用（不是 Catact 的桥）。\n\n"
                            "请关掉占用该端口的程序，或在 config.json 里把 port 改成 1502，\n"
                            "EBPro 那边的端口也要同步改。")
                        return
                finally:
                    self.config(cursor="")

            self.mx_up = None
            self._link_wait_since = None
            self._link_backup_sent = False
            self._refresh_busy_until = 0.0
            ok, msg = self.bridge.start()
        except Exception as e:
            ok, msg = False, f"启动失败：{e}"
        finally:
            self._starting = False
            self._refresh_buttons()

        self.log(("✓ " if ok else "✗ ") + msg)
        if not ok:
            messagebox.showerror(T("menu_start"), msg)
            return
        self.after(1500, lambda: self.toggle_window("M") if "M" not in self.windows else None)

    def stop_bridge(self):
        if self.bridge.running:
            self.log("正在停止桥…")
            self.bridge.stop()
            self.log("桥已停止")
        else:
            orphans, others = self._bridges_on_port()
            if orphans:
                pids = self._kill_bridges(orphans)
                self.log(f"[清理] 结束残留的桥进程 PID {', '.join(map(str, pids))}")
                self._wait_port_free(2.0)
            elif others:
                self.log(f"[清理] 端口被另一个 Catact 的桥占用（PID {others[0]['pid']}），请关掉那个窗口")
            else:
                self.log("桥没有在运行")
        self.link_ok = False
        self.mx_up = None
        self._link_wait_since = None
        self._link_backup_sent = False
        self._refresh_busy_until = 0.0
        self._refresh_buttons()

    def refresh_link(self):
        """⟳ 刷新：让桥立即重新连接 GX 仿真，不停止桥、不重启进程、不断开 EBPro。

        这是「自动重连」之外的手动兜底：正常情况下桥自己会盯着 GX 仿真进程，
        仿真一启动就自动连接；只有自动连接没成功、或想立刻强制重连时才点它。
        """
        if not self.bridge.running:
            self.log("桥没有在运行，请先点「▶ 启动桥」")
            self._refresh_buttons()
            return
        now = time.time()
        if now < self._refresh_busy_until:      # 2 秒内重复点击直接忽略
            return
        self._refresh_busy_until = now + 2.0
        self._refresh_seq += 1
        seq = self._refresh_seq
        self.mx_up = None
        try:
            with open(LINK_REQ_PATH, "w", encoding="utf-8") as f:
                f.write(str(now))
        except OSError as e:
            self.log(f"刷新请求写入失败：{e}")
            self._refresh_busy_until = 0.0
            self._refresh_buttons()
            return
        self.log("⟳ 已请求重新连接 GX 仿真（桥不中断，EBPro 无需重连）")
        self._set_led(YELLOW)
        self.lbl_conn.config(text=T("conn_connecting"), fg="#000000")
        self._refresh_buttons()
        self.after(4000, lambda s=seq: self._refresh_timeout(s))

    def _refresh_timeout(self, seq):
        """刷新请求发出 4 秒后仍没收到桥的状态回报 → 提示桥可能卡住。"""
        if seq != self._refresh_seq or not self.bridge.running:
            return
        if self.mx_up is None:
            self.log("⟳ 刷新请求发出 4 秒仍未收到桥的状态回报。"
                     "桥可能卡在 MX 调用上，可点「■ 停止桥」再「▶ 启动桥」；"
                     "若反复出现，请把这段日志发给我。")

    def _set_btn(self, btn, enabled, on_bg, on_fg="#000000"):
        """统一按钮的可用/禁用外观：禁用时底色回到系统灰、文字转灰、箭头光标。"""
        btn.config(state="normal" if enabled else "disabled",
                   bg=on_bg if enabled else BG,
                   fg=on_fg if enabled else "#808080",
                   disabledforeground="#808080",
                   cursor="hand2" if enabled else "arrow",
                   relief="raised", bd=2)

    def _refresh_buttons(self):
        """只按「桥进程是否在跑」刷新按钮，绝不读取按钮自身状态（避免状态自锁）。"""
        st = button_states(self.bridge.running, self._starting)
        self._set_btn(self.btn_start, st["start"] == "normal", GREEN, "#ffffff")
        self._set_btn(self.btn_stop, st["stop"] == "normal", RED, "#ffffff")
        refresh_on = (st["refresh"] == "normal"
                      and time.time() >= self._refresh_busy_until)
        self._set_btn(self.btn_refresh, refresh_on, TITLE_BG, "#000000")

    # ---------- 轮询
    def _poll_loop(self):
        c = MbClient(self.cfg["host"], self.cfg["port"], timeout=0.7)
        while self.polling:
            wins = [w for w in list(self.windows.values()) if getattr(w, "alive", False)]
            ok_any = False
            for w in wins:
                try:
                    if w.is_bit:
                        vals = c.read_bits(1 if w.area == "0x" else 2, w.base, w.count)
                    else:
                        vals = c.read_words(w.base, w.count)
                    self.result_q.put((w, vals, None))
                    ok_any = True
                except Exception as e:
                    self.result_q.put((w, None, e))
            try:
                y = c.read_bits(2, 1000, 18)
                self.result_q.put(("__Y__", y, None))
                ok_any = True
            except Exception:
                pass
            self.result_q.put(("__LINK__", ok_any, None))
            time.sleep(max(0.15, self.cfg["refresh_ms"] / 1000.0))

    def _probe_loop(self):
        """端口探测 + GX 仿真进程检测都放后台。

        port_open() 在桥没启动时会阻塞 200ms，check_gx() 要起 tasklist 子进程，
        两者都不能放在主线程 _tick 里（会重现拖动掉帧）。
        仿真进程每 1.2 秒查一次就够，不必跟着 400ms 轮询每圈都查。"""
        last_sim = 0.0
        while self.polling:
            self.port_ok = self.port_open()
            now = time.time()
            if now - last_sim >= 1.2:
                last_sim = now
                try:
                    sim = bool(self.check_gx())
                except Exception:
                    sim = self._sim_running
                self._sim_running = sim
            time.sleep(0.4 if self.port_ok else 0.9)

    def _tick(self):
        port = self.port_ok
        running = self.bridge.running
        for line in self.bridge.drain():
            if line == "__EXIT__":
                self.mx_up = None
                continue
            # 桥上报的、经过回读验证的 MX 会话状态：解析后不写进日志框，只更新状态灯
            # 用 __MXSTATE__ 前缀，与轮询队列里的 "__LINK__" 标记区分开
            if line.startswith("__MXSTATE__"):
                state = line[len("__MXSTATE__"):].strip()
                self._state_ver += 1
                if state == "UP":
                    self.mx_up = True
                    self.log("✓ 已连接 GX 仿真")
                elif state == "DOWN":
                    self.mx_up = False
                    self.log("… 未连接 GX 仿真（仿真启动后会自动连接，也可点 ⟳ 刷新）")
                continue
            self.log(line)
        while True:
            try:
                w, vals, err = self.result_q.get_nowait()
            except queue.Empty:
                break
            if w == "__Y__":
                self._apply_output(vals)
            elif w == "__LINK__":
                self.link_ok = bool(vals)
            elif vals is None:
                if port:
                    w.apply_error()
                else:
                    w.apply_neutral()
            else:
                w.apply(vals)

        # 状态灯只认「桥上报且已回读验证」的 MX 状态：
        #   True=绿；False/None=黄（等待或正在连接）。不再靠端口通就判绿，
        #   避免会话已死但 502 还在监听时的假绿。
        if running and port:
            if self.mx_up is True:
                self._set_led(GREEN)
                self.lbl_conn.config(text=T("conn_connected"), fg="#000000")
            elif self.mx_up is False:
                self._set_led(YELLOW)
                self.lbl_conn.config(text=T("conn_waiting"), fg="#000000")
            else:
                self._set_led(YELLOW)
                self.lbl_conn.config(text=T("conn_connecting"), fg="#000000")
        elif running:
            self._set_led(YELLOW)
            self.lbl_conn.config(text=T("conn_starting"), fg="#000000")
        elif port:
            self._set_led(YELLOW)
            self.lbl_conn.config(text=T("conn_port_busy"), fg="#000000")
        else:
            self._set_led("#b0b0b0")
            self.lbl_conn.config(text=T("conn_not_started"), fg="#000000")

        # 仿真进程实时状态
        if self._sim_running:
            self._set_sim_led(GREEN)
            self.lbl_sim.config(text=T("sim_running"), fg="#000000")
        elif self._sim_running is False:
            self._set_sim_led(YELLOW)
            self.lbl_sim.config(text=T("sim_not_running"), fg="#000000")
        else:
            self._set_sim_led("#b0b0b0")
            self.lbl_sim.config(text=T("detecting"), fg="#000000")

        # 自动重连兜底：仿真在跑、桥也在跑，但 5 秒还没连上 → 补发一次刷新请求。
        # 正常情况下桥自己会连上，这里只是防止桥的进程检测被系统策略挡住。
        if running and self._sim_running and self.mx_up is not True:
            if self._link_wait_since is None:
                self._link_wait_since = time.time()
            elif (not self._link_backup_sent
                  and time.time() - self._link_wait_since >= 5.0):
                self._link_backup_sent = True
                try:
                    with open(LINK_REQ_PATH, "w", encoding="utf-8") as f:
                        f.write(str(time.time()))
                    self.log("● 仿真运行中但桥 5 秒未连上，已自动补发一次重连请求")
                except OSError:
                    pass
        else:
            self._link_wait_since = None
            if self.mx_up is True or not running or not self._sim_running:
                self._link_backup_sent = False

        self.lbl_st_bridge.config(text=T("status_bridge_running") if running
                                  else T("status_bridge_stopped"))
        self.lbl_st_addr.config(text=T("status_addr", host=self.cfg["host"],
                                       port=self.cfg["port"],
                                       station=self.cfg["station"]))
        self.lbl_st_mode.config(text=T("status_mode"))
        self.lbl_st_alarm.config(text=T("status_alarms", n=self._alarm_count))
        self.lbl_st_time.config(text=time.strftime("%Y-%m-%d %H:%M:%S"))
        self._refresh_buttons()
        self.after(300, self._tick)

    def _apply_output(self, bits):
        for lbl, v in zip(self.out_labels, bits):
            if v:
                lbl.config(bg=GREEN, fg="#ffffff")
            else:
                lbl.config(bg=WHITE, fg="#000000")

    def port_open(self):
        try:
            s = socket.create_connection((self.cfg["host"], self.cfg["port"]), timeout=0.2)
            s.close()
            return True
        except OSError:
            return False

    # ---------- 环境
    def check_gx(self):
        """检查 GX Simulator3 进程是否存在。

        注意不能用 text=True：中文 Windows 的 tasklist 输出是 GBK，
        UTF-8 模式解释器会抛解码异常，导致仿真检测永久失效。
        直接在原始 bytes 里找进程名（ASCII）即可。"""
        try:
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq FSimRun3.exe",
                                  "/FO", "CSV", "/NH"],
                                 capture_output=True, timeout=5,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return b"FSIMRUN3" in (out.stdout or b"").upper()
        except Exception:
            return False

    def mx_installed(self):
        try:
            winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"ActUtlType.ActUtlType")
            return True
        except OSError:
            return False

    def _mx_registry_dirs(self):
        """从已安装程序注册表里找 MELSOFT / MX Component 的安装目录。"""
        dirs = []
        roots = [
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE,
             r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER,
             r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for root, path in roots:
            try:
                with winreg.OpenKey(root, path) as k:
                    for i in range(winreg.QueryInfoKey(k)[0]):
                        try:
                            name = winreg.EnumKey(k, i)
                            with winreg.OpenKey(k, name) as sk:
                                try:
                                    dn = str(winreg.QueryValueEx(sk, "DisplayName")[0])
                                except OSError:
                                    continue
                                low = dn.lower()
                                if not any(x in low for x in
                                           ("mx component", "melsoft", "gx works")):
                                    continue
                                try:
                                    loc = str(winreg.QueryValueEx(sk, "InstallLocation")[0])
                                except OSError:
                                    loc = ""
                                if loc and os.path.isdir(loc):
                                    dirs.append(loc)
                        except OSError:
                            continue
            except OSError:
                continue
        return dirs

    def find_mx_utility(self, force=False):
        """自动定位 Communication Settings Utility（ActComm.exe）。

        顺序：config 记住的路径 → 常见安装路径 → 注册表 InstallLocation
        → MELSOFT 目录下有限深度遍历。结果缓存，Recheck 时 force=True 重找。
        """
        if not force and self._mx_util_cache is not None:
            return self._mx_util_cache or None

        cfgp = (self.cfg.get("mx_utility") or "").strip()
        if cfgp and os.path.exists(cfgp):
            self._mx_util_cache = cfgp
            return cfgp

        cands = []
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env)
            if base:
                cands.append(os.path.join(base, "MELSOFT", "ACT", "Utl", "ActComm.exe"))
        for d in "CDEFG":
            cands.append(f"{d}:\\Program Files (x86)\\MELSOFT\\ACT\\Utl\\ActComm.exe")
            cands.append(f"{d}:\\Program Files\\MELSOFT\\ACT\\Utl\\ActComm.exe")

        for base in self._mx_registry_dirs():
            for rel in (r"ACT\Utl\ActComm.exe", r"Utl\ActComm.exe", "ActComm.exe"):
                cands.append(os.path.join(base, rel))

        # MELSOFT 目录下有限深度搜索（只找 ActComm.exe，最多 4 层）
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            base = os.environ.get(env)
            if not base:
                continue
            root = os.path.join(base, "MELSOFT")
            if not os.path.isdir(root):
                continue
            for cur, dirs, files in os.walk(root):
                if cur[len(root):].count(os.sep) >= 4:
                    dirs[:] = []
                if "ActComm.exe" in files:
                    cands.append(os.path.join(cur, "ActComm.exe"))

        for p in cands:
            if p and os.path.exists(p):
                self._mx_util_cache = p
                if self.cfg.get("mx_utility") != p:
                    self.cfg["mx_utility"] = p
                    self.save_cfg()
                return p

        self._mx_util_cache = ""
        return None

    def mx_utility_path(self, force=False):
        cfgp = (self.cfg.get("mx_utility") or "").strip()
        if cfgp and os.path.exists(cfgp):
            return cfgp
        p = self.find_mx_utility(force=force)
        return p

    def locate_mx_utility(self):
        """手动定位 ActComm.exe，并把路径写进 config.json。"""
        cur = (self.cfg.get("mx_utility") or "").strip()
        init = os.path.dirname(cur) if cur and os.path.isdir(os.path.dirname(cur)) else ""
        if not init:
            for env in ("ProgramFiles(x86)", "ProgramFiles"):
                base = os.environ.get(env)
                if base:
                    cand = os.path.join(base, "MELSOFT", "ACT", "Utl")
                    if os.path.isdir(cand):
                        init = cand
                        break
        if not init:
            init = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles") or "C:\\"

        path = filedialog.askopenfilename(
            parent=self, title=T("mx_locate_title"), initialdir=init,
            filetypes=[("ActComm.exe", "ActComm.exe"), ("Executable", "*.exe")])
        if not path:
            return
        if os.path.basename(path).lower() != "actcomm.exe":
            if not messagebox.askyesno(
                    T("mx_dialog_title"),
                    T("mx_not_actcomm", name=os.path.basename(path))):
                return
        self.cfg["mx_utility"] = path
        self._mx_util_cache = path
        self.save_cfg()
        self._update_mx_state()
        self.log(f"已记住 MX 设置工具路径：{path}")
        self.set_hint(f"MX Utility: {path}")

    def open_mx_utility(self):
        p = self.mx_utility_path()
        if not p:
            self.log("未找到 MX Communication Settings Utility")
            if messagebox.askyesno(T("mx_dialog_title"), T("mx_not_found_msg")):
                self.locate_mx_utility()
                p = self.mx_utility_path(force=True)
            if not p:
                return
        try:
            subprocess.Popen([p], cwd=os.path.dirname(p))
            self.log(f"已打开 MX 设置工具：{p}")
            self.set_hint(f"{T('mx_open')}: {p}")
        except Exception as e:
            messagebox.showerror(T("mx_dialog_title"),
                                 T("mx_open_fail", err=e))

    def mx_env_check(self):
        self._update_mx_state(force=True)
        path = self.mx_utility_path() or T("path_missing")
        txt = (f"MX Component: {T('installed') if self.mx_installed() else T('not_installed')}\n"
               f"{T('mx_utility_label')}: {path}\n"
               f"{T('python_label')}: "
               f"{T('ready') if os.path.exists(self.cfg['python32']) else T('missing')}\n"
               f"{T('sim_label')}: "
               f"{T('sim_ok') if self.check_gx() else T('sim_none')}")
        self.log("—— MX 环境检查 ——")
        for line in txt.splitlines():
            self.log(line)
        messagebox.showinfo(T("mx_check_title"),
                            txt + "\n\n" + T("mx_check_extra"))

    def bridge_settings(self):
        win = tk.Toplevel(self)
        win.title(T("bridge_settings_title"))
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        win.geometry("400x200")
        vals = [(T("port_setting"), self.cfg["port"]),
                (T("station_setting"), self.cfg["station"])]
        entries = []
        for i, (label, val) in enumerate(vals):
            tk.Label(win, text=label, bg=BG, fg="#000000", font=FONT).grid(
                row=i, column=0, padx=14, pady=8, sticky="w")
            e = tk.Entry(win, width=22, font=FONT, relief="sunken", bd=2,
                         bg=WHITE, fg="#000000")
            e.insert(0, str(val))
            e.grid(row=i, column=1, padx=8, pady=8, sticky="w")
            entries.append(e)

        def save():
            try:
                self.cfg["port"] = int(entries[0].get())
                self.cfg["station"] = int(entries[1].get())
                self.save_cfg()
                self.lbl_port.config(text=str(self.cfg["port"]))
                self.lbl_st.config(text=str(self.cfg["station"]))
                win.destroy()
                self.log("桥参数已保存（重启桥生效）")
            except ValueError:
                messagebox.showerror(T("bridge_settings_title"), T("err_int"))

        tk.Button(win, text=T("save"), command=save, width=10, font=FONT,
                  bg=BAR, fg="#000000", relief="raised", bd=2,
                  padx=4, pady=2).grid(row=2, column=1, pady=14, sticky="e")

    def export_all(self):
        if not self.windows:
            messagebox.showinfo(T("export_title"), T("no_window"))
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile="monitor.csv")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write("元件,EBPro地址,值\n")
                for w in self.windows.values():
                    seg = AddrMap.segment(w.area, w.dev)
                    for i, cell in enumerate(w.cells):
                        num = w.start + i
                        name = f"{w.dev}{AddrMap.fmt(w.dev, num)}"
                        f.write(f"{name},{w.area}{seg[0] + num},{cell.cget('text')}\n")
            self.log(f"已导出：{path}")
        except Exception as e:
            messagebox.showerror(T("export_title"), str(e))

    def show_help(self):
        messagebox.showinfo(T("usage_title"), T("help_body"))

    def show_about(self):
        messagebox.showinfo(T("about_title"), T("about_body", ver=APP_VERSION))
    def on_close(self):
        self.polling = False
        try:
            self.bridge.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    if "--demo" in sys.argv:
        app.after(400, lambda: [app.toggle_window("M"), app.toggle_window("Y")])
        app.after(600, app.open_convert)
    app.mainloop()
