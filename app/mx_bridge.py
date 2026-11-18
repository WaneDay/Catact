# -*- coding: utf-8 -*-
"""
MX Component -> Modbus TCP 桥（通用软元件版）

链路：
    GX Works3 (FX5U) --仿真--> GX Simulator3
        |  MX Component（逻辑站号 1）
    本脚本  --Modbus TCP 127.0.0.1:502-->  EBPro

设计原则：三菱的软元件种类很多（M/D/X/Y/T/C/W…），但 Modbus 只有 4 个区。
所以这里把每个区切成固定段落，一次性定死，以后不管用哪种元件，都不用改代码。

地址表（EBPro 里填的是「显示值」，从 1 开始）：

  0x 线圈（可读可写）
      1 – 8000      M0 – M7999
      8001 – 9000   S0 – S999
      9001 – 10000  B0 – B3E7      （B 是十六进制编号）
      10001 – 11000 X0 – X1777     （X 可写镜像，八进制）
      11001 – 12000 Y0 – Y1777     （Y 可写镜像，八进制）
      12001 – 19000 T/C/L/SM/F/ST/SB 可写镜像
                    （规则：0x 地址 = 1x 地址 + 10000）

  1x 离散输入（只读，指示灯用）
      1 – 1000      X0 – X1777      （X 是八进制编号）
      1001 – 2000   Y0 – Y1777      （Y 是八进制编号）
      2001 – 3000   T0 – T999 触点
      3001 – 4000   C0 – C999 触点
      4001 – 9000   L / SM / F / ST / SB 触点
      注：0x 与 1x 的编号是重叠的（0x 1 = M0，1x 1 = X0）。FC05/FC0F
          只能写 0x；HMI 若把开关绑成 1x，写入会落到同号的 M/S/B，
          桥会打 [地址提示] 告诉你这个开关应该改成哪个 0x 地址。

  4x 保持寄存器（可读可写）
      1 – 8000      D0 – D7999
      8001 – 9000   W0 – W999
      9001 – 10000  T0 – T999 当前值
      10001 – 11000 C0 – C999 当前值

要点：
  * 按需读取，不轮询全表，地址范围只受 PLC 本身限制
  * 位元件（M/X/Y/T/C 触点）在 MX 里是「16 点打包」的，本脚本已自动展开
  * X/Y 编号是八进制：Y7 之后是 Y10
  * 所有写入都会打日志（[写入] / [写入未生效] / [写拒绝] / [写失败]），
    GUI 日志框里直接能看到，按一次按钮就能定位问题

前置条件：
  1. GX Works3「模拟开始」已启动，仿真器 RUN
  2. Communication Settings Utility 里建好逻辑站号（本机是 1）
  3. 32 位 Python + comtypes

用法：
    python mx_bridge.py               # 站号 1，监听 502
    python mx_bridge.py --station 1 --port 502
"""

import argparse
import ctypes as C
import gc
import os
import queue
import socket
import struct
import subprocess
import sys
import threading
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

try:
    from comtypes.client import GetModule, CreateObject
except ImportError:
    print("缺少 comtypes，先执行： python -m pip install comtypes")
    raise SystemExit(1)


VT_I4 = 3
VT_BSTR = 8
VT_BYREF = 0x4000
DISPATCH_METHOD = 1
DISPID_READ_BLOCK = 6

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modbus_debug.log")
LOG_MAX = 2 * 1024 * 1024      # 2 MB 轮转，避免长期运行把日志撑爆
_log_count = 0


def log(msg, echo=False):
    """写日志文件；echo=True 时同时打到 stdout（GUI 的日志框能看到）。
    写入/拒绝这类关键事件一律 echo，按一次 EBPro 按钮就能看清发生了什么。"""
    global _log_count
    line = time.strftime("%H:%M:%S ") + msg
    if echo:
        print(line, flush=True)
    _log_count += 1
    try:
        if _log_count % 200 == 0 and os.path.getsize(LOG_PATH) > LOG_MAX:
            try:
                os.replace(LOG_PATH, LOG_PATH + ".1")
            except OSError:
                os.remove(LOG_PATH)
    except OSError:
        pass
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


oleaut32 = C.OleDLL("oleaut32")
oleaut32.SysAllocString.restype = C.c_void_p
oleaut32.SysAllocString.argtypes = [C.c_wchar_p]
oleaut32.SysFreeString.argtypes = [C.c_void_p]


class VARIANT(C.Structure):
    _pack_ = 4
    _fields_ = [
        ("vt", C.c_ushort),
        ("wReserved1", C.c_ushort),
        ("wReserved2", C.c_ushort),
        ("wReserved3", C.c_ushort),
        ("p", C.c_void_p),
        ("pad", C.c_uint),
    ]


class DISPPARAMS(C.Structure):
    _fields_ = [
        ("rgvarg", C.POINTER(VARIANT)),
        ("rgdispidNamedArgs", C.POINTER(C.c_long)),
        ("cArgs", C.c_uint),
        ("cNamedArgs", C.c_uint),
    ]


_INVOKE_PROTO = C.WINFUNCTYPE(
    C.HRESULT, C.c_void_p, C.c_long, C.c_void_p, C.c_ulong, C.c_ushort,
    C.POINTER(DISPPARAMS), C.POINTER(VARIANT), C.c_void_p, C.POINTER(C.c_uint),
)


def find_tlb():
    rel = ("MELSOFT", "ACT", "Control", "ActUtlType.tlb")
    roots = []
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        v = os.environ.get(env)
        if v:
            roots.append(v)
    for drive in "CDEFGH":
        roots.append(f"{drive}:\\Program Files (x86)")
        roots.append(f"{drive}:\\Program Files")
    for r in roots:
        p = os.path.join(r, *rel)
        if os.path.exists(p):
            return p
    return None


def rc_text(rc):
    """把 MX 返回码格式化成日志好看的样子（None/字符串也兼容）。"""
    if rc is None:
        return "未知"
    if isinstance(rc, str):
        return rc
    try:
        return f"0x{int(rc) & 0xFFFFFFFF:08X}"
    except (TypeError, ValueError):
        return str(rc)


class Mx:
    """MX Component 封装：块读走底层 IDispatch::Invoke，其余用普通调用。"""

    def __init__(self, station, tlb=None):
        tlb = tlb or find_tlb()
        if not tlb:
            raise RuntimeError("找不到 ActUtlType.tlb，请用 --tlb 指定路径")
        self.mod = GetModule(tlb)
        self.iid_null = (C.c_byte * 16)()
        self.station = station
        self.connected = False
        self.last_rc = None
        self.act = None
        self.pdisp = None
        self.invoke = None
        self._make()
        # 启动时只快速试 2 次：GX 仿真可能还没 RUN，不能卡住 502 监听。
        # 真正的重连交给 link_watchdog，它会一直试到仿真启动并连上为止。
        self.connected = self._open(tries=2, gap=0.5)
        if self.connected:
            # Open 返回 0 不等于会话真的可用：必须回读一个软元件确认。
            # 1.0.3 就是少了这一步，仿真重启后会「状态灯变绿但数据不动」。
            self.connected = self.verify(tries=2, gap=0.2)
        if not self.connected:
            print(f"[MX] 初始未连上（rc={rc_text(self.last_rc)}），等待自动重连", flush=True)

    def _make(self):
        """创建一个全新的 ActUtlType 实例并绑定逻辑站号。

        重连时必须走这里，而不是对旧对象 Close/Open —— 那等于在已经失效的
        会话上原地重开；仿真器换了进程/实例后，旧 COM 对象会「Open 成功、
        读取失败」。新建实例等价于「关掉桥再启动桥」，是实测有效的做法。"""
        self.act = CreateObject("ActUtlType.ActUtlType",
                                interface=self.mod.IActUtlType)
        self.act.ActLogicalStationNumber = self.station
        self.pdisp = C.cast(self.act, C.c_void_p).value
        vtbl = C.cast(self.pdisp, C.POINTER(C.POINTER(C.c_void_p))).contents
        self.invoke = _INVOKE_PROTO(vtbl[6])

    def _drop_session(self):
        """丢弃当前 COM 实例（不调用可能阻塞的 Close），下轮用新实例重连。"""
        old = self.act
        self.act = None
        self.pdisp = None
        self.invoke = None
        self.connected = False
        if old is not None:
            del old
            try:
                gc.collect()
            except Exception:
                pass

    def invalidate(self):
        """仿真停止时作废会话（在 Worker 线程里调用）。"""
        self._drop_session()

    def read_block(self, dev, size):
        buffer = (C.c_long * size)()
        bstr = oleaut32.SysAllocString(dev)
        try:
            args = (VARIANT * 3)()
            args[0].vt = VT_I4 | VT_BYREF
            args[0].p = C.cast(buffer, C.c_void_p)
            args[1].vt = VT_I4
            args[1].p = C.c_void_p(size)
            args[2].vt = VT_BSTR
            args[2].p = C.c_void_p(bstr)

            params = DISPPARAMS()
            params.rgvarg = C.cast(args, C.POINTER(VARIANT))
            params.cArgs = 3
            params.cNamedArgs = 0

            result = VARIANT()
            arg_err = C.c_uint(0)
            hr = self.invoke(
                C.c_void_p(self.pdisp), DISPID_READ_BLOCK,
                C.cast(self.iid_null, C.c_void_p), 0, DISPATCH_METHOD,
                C.byref(params), C.byref(result), None, C.byref(arg_err),
            )
            if hr != 0:
                raise RuntimeError(f"ReadDeviceBlock({dev},{size}) HRESULT=0x{hr & 0xFFFFFFFF:08X}")
            rc = result.p or 0
            return [v & 0xFFFF for v in buffer], rc
        finally:
            oleaut32.SysFreeString(C.c_void_p(bstr))

    def set(self, dev, value):
        return self.act.SetDevice(dev, int(value))

    def _open(self, tries=1, gap=0.0):
        """尝试 Open，成功返回 True，失败返回 False —— 绝不抛异常。
        看门狗会周期性调用它，所以仿真器没 RUN 时也不能拖慢整轮循环。"""
        rc = None
        for _ in range(max(1, tries)):
            try:
                rc = self.act.Open()
            except Exception as e:
                self.last_rc = f"异常：{e}"
                rc = -1
            if rc == 0:
                self.last_rc = 0
                return True
            if gap:
                time.sleep(gap)
        self.last_rc = rc
        return False

    def reconnect(self):
        """重建会话：丢弃旧实例 → 新实例 → Open → 回读校验。

        返回 True 才代表「真的能用」；Open 成功但读不到数据时返回 False，
        由看门狗稍后重试，绝不会向 GUI 上报一个假的「已连接」。"""
        self._drop_session()
        time.sleep(0.15)
        try:
            self._make()
        except Exception as e:
            self.last_rc = f"创建实例失败：{e}"
            return False
        self.connected = self._open(tries=3, gap=0.3)
        if not self.connected:
            return False
        self.connected = self.verify(tries=2, gap=0.25)
        return self.connected

    reopen = reconnect          # 兼容旧名字（1.0.3 的 link_watchdog 用过）

    def verify(self, tries=2, gap=0.25):
        """回读校验：读 D0，rc==0 才算会话可用。"""
        for i in range(max(1, tries)):
            try:
                if self.probe():
                    return True
            except Exception:
                pass
            if i + 1 < tries:
                time.sleep(gap)
        return False

    def probe(self):
        """会话健康探测：读一个肯定合法的软元件 D0。
        仿真 STOP / 重启 / RUN 切换后，MX 的 ReadDeviceBlock 会返回非 0 或抛异常，
        据此判定旧会话已失效，需要重连。"""
        try:
            _, rc = self.read_block("D0", 1)
            return rc == 0
        except Exception:
            return False

    def close(self):
        try:
            if self.act is not None:
                self.act.Close()
        except Exception:
            pass


class Worker(threading.Thread):
    """独占 COM 的工作线程，避免跨线程调用 MX 对象。"""

    def __init__(self, mx):
        super().__init__(daemon=True)
        self.mx = mx
        self.q = queue.Queue()
        # 多个 EBPro 连接会各自起 client_worker 线程，底层 COM 只能串行调用
        self.lock = threading.Lock()

    def run(self):
        # 重连时会在这个线程里新建 ActUtlType COM 实例，必须先初始化 COM 套间；
        # 否则 CreateObject 直接报「尚未调用 CoInitialize (-2147221008)」。
        inited = False
        try:
            inited = C.windll.ole32.CoInitializeEx(None, 0x2) in (0, 1)   # STA
        except Exception:
            inited = False
        try:
            while True:
                job = self.q.get()
                if job is None:
                    return
                fn, args, box = job
                try:
                    box["data"] = fn(*args)
                    box["ok"] = True
                except Exception as e:
                    box["err"] = e
                    box["ok"] = False
                box["evt"].set()
        finally:
            if inited:
                try:
                    C.windll.ole32.CoUninitialize()
                except Exception:
                    pass

    def call(self, fn, *args, timeout=5.0):
        box = {"evt": threading.Event()}
        with self.lock:
            self.q.put((fn, args, box))
            if not box["evt"].wait(timeout):
                raise TimeoutError("MX 调用超时")
        if not box["ok"]:
            raise box["err"]
        return box["data"]

    def stop(self):
        self.q.put(None)


# ---------------------------------------------------------------- 地址映射

# (起始显示值, 结束显示值, 软元件前缀)
# 0x = 可写位（FC05/FC0F 写入）。除了 M/S/B，还提供 1x 全部只读区的「可写镜像」：
#     0x 地址 = 1x 地址 + 10000（例：X0 按钮 → 0x 10001，Y10 按钮 → 0x 11009，L0 → 0x 14001）
#     注意 X/Y 写入只在仿真器里有意义（真机的 X 由外部输入驱动）；T/C 触点、SM/F 等
#     由 PLC 程序驱动，写入可能被拒绝。
BIT_MAP = {
    "0x": [
        (1, 8000, "M"),          # 内部继电器
        (8001, 9000, "S"),       # 步进继电器
        (9001, 10000, "B"),      # 链接继电器（十六进制）
        (10001, 11000, "X"),     # 输入（可写镜像，八进制）
        (11001, 12000, "Y"),     # 输出（可写镜像，八进制）
        (12001, 13000, "T"),     # 定时器触点（可写镜像）
        (13001, 14000, "C"),     # 计数器触点（可写镜像）
        (14001, 15000, "L"),     # 锁存继电器（可写镜像）
        (15001, 16000, "SM"),    # 特殊继电器（可写镜像）
        (16001, 17000, "F"),     # 报警器（可写镜像）
        (17001, 18000, "ST"),    # 累计定时器触点（可写镜像）
        (18001, 19000, "SB"),    # 链接特殊继电器（可写镜像，十六进制）
    ],
    # 1x = 只读位
    "1x": [
        (1, 1000, "X"),          # 输入（八进制）
        (1001, 2000, "Y"),       # 输出（八进制）
        (2001, 3000, "T"),       # 定时器触点
        (3001, 4000, "C"),       # 计数器触点
        (4001, 5000, "L"),       # 锁存继电器
        (5001, 6000, "SM"),      # 特殊继电器
        (6001, 7000, "F"),       # 报警器
        (7001, 8000, "ST"),      # 累计定时器触点
        (8001, 9000, "SB"),      # 链接特殊继电器（十六进制）
    ],
}
WORD_MAP = {
    "4x": [
        (1, 8000, "D"),          # 数据寄存器
        (8001, 9000, "W"),       # 链接寄存器（十六进制）
        (9001, 10000, "T"),      # 定时器当前值
        (10001, 11000, "C"),     # 计数器当前值
        (11001, 12000, "ST"),    # 累计定时器当前值
        (12001, 13000, "SD"),    # 特殊寄存器
        (13001, 21000, "ZR"),    # 文件寄存器（仿真器不支持）
        (21001, 21020, "Z"),     # 变址寄存器
        (22001, 30000, "R"),     # 文件寄存器 R
        (30001, 31000, "SW"),    # 链接特殊寄存器（十六进制）
    ],
}

OCTAL_DEV = {"X", "Y"}
HEX_DEV = {"W", "B", "SW", "SB"}


def resolve(area, addr):
    """addr 是 EBPro 发来的原始地址（0 起），返回 (设备前缀, 段内序号)"""
    display = addr + 1
    table = BIT_MAP.get(area) or WORD_MAP.get(area) or []
    for start, end, dev in table:
        if start <= display <= end:
            return dev, display - start
    return None, None


def devname(dev, index):
    if dev in OCTAL_DEV:
        return f"{dev}{index:o}"
    if dev in HEX_DEV:
        return f"{dev}{index:X}"
    return f"{dev}{index}"


class Plc:
    def __init__(self, worker):
        self.w = worker

    def read_words(self, dev, start, count):
        vals, rc = self.w.call(self.w.mx.read_block, devname(dev, start), count)
        if rc != 0:
            raise RuntimeError(f"read {dev}{start} rc={rc}")
        return vals

    def read_bits(self, dev, index, qty):
        """位元件按 16 点打包，这里对齐后展开"""
        aligned = (index // 16) * 16
        need = ((index - aligned) + qty + 15) // 16
        words = self.read_words(dev, aligned, need)
        bits = []
        for i in range(qty):
            k = index - aligned + i
            w = words[k // 16] if k // 16 < len(words) else 0
            bits.append((w >> (k % 16)) & 1)
        return bits

    def write_bits(self, dev, index, values, verify=True):
        """逐点写位。SetDevice 的返回码必须检查——以前忽略返回值，
        写失败也回 Modbus 成功，EBPro 就会「按一下又弹回」且日志一片空白。
        verify=True 时回读一次，返回回读值列表（回读失败返回 None）。"""
        for i, v in enumerate(values):
            name = devname(dev, index + i)
            rc = self.w.call(self.w.mx.set, name, 1 if v else 0)
            if rc:
                raise RuntimeError(f"{name} 写入返回 rc=0x{rc & 0xFFFFFFFF:08X}")
        if not verify:
            return None
        try:
            return self.read_bits(dev, index, len(values))
        except Exception:
            return None

    def write_words(self, dev, index, values, verify=True):
        for i, v in enumerate(values):
            name = devname(dev, index + i)
            rc = self.w.call(self.w.mx.set, name, v & 0xFFFF)
            if rc:
                raise RuntimeError(f"{name} 写入返回 rc=0x{rc & 0xFFFFFFFF:08X}")
        if not verify:
            return None
        try:
            return self.read_words(dev, index, len(values))
        except Exception:
            return None


def seg_at(table, display):
    for s, e, d in table:
        if s <= display <= e:
            return s, e, d
    return None


def pick_write_seg(addr):
    """PDU 地址 → 0x 可写段。

    注意：0x 和 1x 的编号是重叠的（0x 1 = M0，而 1x 1 = X0）。
    FC05/FC0F 只能按 0x 解释，无法从地址本身判断用户想写 1x。
    所以 HMI 里绑定 1x 的开关，写入会落到同号的 M/S/B 上（例如 1x 1 →
    M0），而读回读的是 1x 1（X0）→ 永远不变，表现就是「一按就回弹」。
    下面 note_1x_read / hint_area_mismatch 专门把这种配置错误指出来。"""
    return seg_at(BIT_MAP["0x"], addr + 1)


# 最近被读过的 1x 显示地址：写入时用来提示「HMI 还在用 1x 地址」
_recent_1x = {}
_recent_lock = threading.Lock()
RECENT_TTL = 15.0


def note_1x_read(addr, qty):
    now = time.time()
    with _recent_lock:
        if len(_recent_1x) > 8192:
            _recent_1x.clear()
        for i in range(qty):
            _recent_1x[addr + 1 + i] = now


def hint_area_mismatch(display, actual_name):
    """写入落到 0x 时，如果同一个号刚才被当 1x 读过，给出改地址提示。"""
    now = time.time()
    with _recent_lock:
        ts = _recent_1x.get(display)
    if not ts or now - ts > RECENT_TTL:
        return
    dev, idx = resolve("1x", display - 1)
    if not dev:
        return
    log(f"[地址提示] HMI 正在读 1x {display}（{devname(dev, idx)}），"
        f"但这次写入落到了 0x {display}（{actual_name}）。"
        f"如果这个开关是要控制 {devname(dev, idx)}，请把 HMI 地址改成 0x {display + 10000}。",
        echo=True)


def read_bits_range(plc, area, addr, qty):
    """EBPro 常按 32 字整块读，块会跨过区段边界，这里有逐段拆分"""
    table = BIT_MAP[area]
    out, pos, left = [], addr, qty
    while left > 0:
        seg = seg_at(table, pos + 1)
        if not seg:
            nxt = min([s for s, e, d in table if s > pos + 1], default=None)
            if nxt is None:
                out.extend([0] * left)
                break
            skip = min(left, nxt - (pos + 1))
            out.extend([0] * skip)
            pos += skip
            left -= skip
            continue
        s, e, dev = seg
        take = min(left, e - (pos + 1) + 1)
        out.extend(plc.read_bits(dev, (pos + 1) - s, take))
        pos += take
        left -= take
    return out


def read_words_range(plc, area, addr, qty):
    table = WORD_MAP[area]
    out, pos, left = [], addr, qty
    while left > 0:
        seg = seg_at(table, pos + 1)
        if not seg:
            nxt = min([s for s, e, d in table if s > pos + 1], default=None)
            if nxt is None:
                out.extend([0] * left)
                break
            skip = min(left, nxt - (pos + 1))
            out.extend([0] * skip)
            pos += skip
            left -= skip
            continue
        s, e, dev = seg
        take = min(left, e - (pos + 1) + 1)
        out.extend(plc.read_words(dev, (pos + 1) - s, take))
        pos += take
        left -= take
    return out


# ---------------------------------------------------------------- Modbus

def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf


def exc_pdu(fc, code=0x02):
    return bytes([(fc | 0x80) & 0xFF, code])


def handle_pdu(pdu, plc):
    if not pdu:
        return None
    fc = pdu[0]

    # 读：0x 线圈 / 1x 离散输入
    if fc in (0x01, 0x02):
        if len(pdu) < 5:
            return exc_pdu(fc, 0x03)
        addr, qty = struct.unpack(">HH", pdu[1:5])
        if qty < 1 or qty > 2000:
            return exc_pdu(fc, 0x03)
        area = "0x" if fc == 0x01 else "1x"
        try:
            bits = read_bits_range(plc, area, addr, qty)
        except Exception as e:
            log(f"[读失败] {area} addr={addr} qty={qty} {e}")
            return exc_pdu(fc, 0x04)
        if fc == 0x02:
            note_1x_read(addr, qty)
        buf = bytearray((qty + 7) // 8)
        for i, b in enumerate(bits):
            if b:
                buf[i // 8] |= 1 << (i % 8)
        return bytes([fc, len(buf)]) + bytes(buf)

    # 读：4x 保持寄存器
    if fc in (0x03, 0x04):
        if len(pdu) < 5:
            return exc_pdu(fc, 0x03)
        addr, qty = struct.unpack(">HH", pdu[1:5])
        if qty < 1 or qty > 125:
            return exc_pdu(fc, 0x03)
        try:
            words = read_words_range(plc, "4x", addr, qty)
        except Exception as e:
            log(f"[读失败] 4x addr={addr} qty={qty} {e}")
            return exc_pdu(fc, 0x04)
        return bytes([fc, qty * 2]) + b"".join(struct.pack(">H", w & 0xFFFF) for w in words)

    # 写：单个线圈
    if fc == 0x05:
        if len(pdu) < 5:
            return exc_pdu(fc, 0x03)
        addr, val = struct.unpack(">HH", pdu[1:5])
        if val not in (0x0000, 0xFF00):
            return exc_pdu(fc, 0x03)
        seg = pick_write_seg(addr)
        if not seg:
            log(f"[写拒绝] 0x {addr + 1}（不在地址表内，检查 EBPro 地址）", echo=True)
            return exc_pdu(fc, 0x02)
        want = 1 if val == 0xFF00 else 0
        idx = (addr + 1) - seg[0]
        name = devname(seg[2], idx)
        try:
            back = plc.write_bits(seg[2], idx, [want])
        except Exception as e:
            log(f"[写失败] 0x {addr + 1} → {name}={want}：{e}", echo=True)
            return exc_pdu(fc, 0x04)
        if back is not None and (1 if back[0] else 0) != want:
            log(f"[写入未生效] 0x {addr + 1} → {name}={want}，回读={back[0]}"
                "（软元件不可写，或被梯形图/输入刷新立刻改回）", echo=True)
        else:
            log(f"[写入] 0x {addr + 1} → {name}={want}", echo=True)
        hint_area_mismatch(addr + 1, name)
        return pdu

    # 写：单个寄存器
    if fc == 0x06:
        if len(pdu) < 5:
            return exc_pdu(fc, 0x03)
        addr, val = struct.unpack(">HH", pdu[1:5])
        seg = seg_at(WORD_MAP["4x"], addr + 1)
        if not seg:
            log(f"[写拒绝] 4x {addr + 1}（不在地址表内，检查 EBPro 地址）", echo=True)
            return exc_pdu(fc, 0x02)
        idx = (addr + 1) - seg[0]
        name = devname(seg[2], idx)
        try:
            back = plc.write_words(seg[2], idx, [val])
        except Exception as e:
            log(f"[写失败] 4x {addr + 1} → {name}={val}：{e}", echo=True)
            return exc_pdu(fc, 0x04)
        if back is not None and (back[0] & 0xFFFF) != (val & 0xFFFF):
            log(f"[写入未生效] 4x {addr + 1} → {name}={val}，回读={back[0]}", echo=True)
        else:
            log(f"[写入] 4x {addr + 1} → {name}={val}", echo=True)
        return pdu

    # 写：多个线圈
    if fc == 0x0F:
        if len(pdu) < 6:
            return exc_pdu(fc, 0x03)
        addr, qty = struct.unpack(">HH", pdu[1:5])
        byte_count = pdu[5]
        if qty < 1 or qty > 1968 or byte_count != (qty + 7) // 8 or len(pdu) < 6 + byte_count:
            return exc_pdu(fc, 0x03)
        targets, missing = [], []
        for i in range(qty):
            seg = pick_write_seg(addr + i)
            if not seg:
                missing.append(addr + i + 1)
            targets.append((seg, i))
        if missing:
            log(f"[写拒绝] 0x {missing[:8]} 不在地址表内（共 {len(missing)} 点）", echo=True)
            return exc_pdu(fc, 0x02)
        verbose = qty <= 8
        for seg, i in targets:
            b = (pdu[6 + i // 8] >> (i % 8)) & 1
            idx = (addr + 1 + i) - seg[0]
            name = devname(seg[2], idx)
            try:
                plc.write_bits(seg[2], idx, [b], verify=False)
            except Exception as e:
                log(f"[写失败] 0x {addr + 1 + i} → {name}={b}：{e}", echo=True)
                return exc_pdu(fc, 0x04)
            if verbose:
                log(f"[写入] 0x {addr + 1 + i} → {name}={b}", echo=True)
                hint_area_mismatch(addr + 1 + i, name)
        if not verbose:
            log(f"[写入] 0x {addr + 1} 起 {qty} 点（多线圈）", echo=True)
        return bytes([fc]) + pdu[1:5]

    # 写：多个寄存器（EBPro 的数值输入走这里）
    if fc == 0x10:
        if len(pdu) < 6:
            return exc_pdu(fc, 0x03)
        addr, qty = struct.unpack(">HH", pdu[1:5])
        byte_count = pdu[5]
        if qty < 1 or qty > 123 or byte_count != qty * 2 or len(pdu) < 6 + byte_count:
            return exc_pdu(fc, 0x03)
        words = list(struct.unpack(">" + "H" * qty, pdu[6:6 + qty * 2]))
        segs = [seg_at(WORD_MAP["4x"], addr + 1 + i) for i in range(qty)]
        if any(s is None for s in segs):
            bad = [addr + 1 + i for i, s in enumerate(segs) if s is None]
            log(f"[写拒绝] 4x {bad[:8]} 不在地址表内（共 {len(bad)} 点）", echo=True)
            return exc_pdu(fc, 0x02)
        verbose = qty <= 8
        for i, w in enumerate(words):
            seg = segs[i]
            idx = (addr + 1 + i) - seg[0]
            name = devname(seg[2], idx)
            try:
                plc.write_words(seg[2], idx, [w], verify=False)
            except Exception as e:
                log(f"[写失败] 4x {addr + 1 + i} → {name}={w}：{e}", echo=True)
                return exc_pdu(fc, 0x04)
            if verbose:
                log(f"[写入] 4x {addr + 1 + i} → {name}={w}", echo=True)
        if not verbose:
            log(f"[写入] 4x {addr + 1} 起 {qty} 个字（多寄存器）", echo=True)
        return bytes([fc]) + pdu[1:5]

    return exc_pdu(fc, 0x01)


def client_worker(conn, peer, plc):
    served = False   # 只有真正发过 Modbus 请求的连接才算客户端会话；
    # GUI 的状态灯探测（连上就关、不带数据）不再打进日志，避免刷屏
    try:
        while True:
            header = recv_exact(conn, 7)
            if not header:
                break
            tid, pid, length, unit = struct.unpack(">HHHB", header)
            body = recv_exact(conn, length - 1)
            if body is None:
                break
            if not served:
                served = True
                print(f"[EBPro 连接] {peer}")
            resp = handle_pdu(body, plc)
            if resp is None:
                break
            conn.sendall(struct.pack(">HHHB", tid, 0, len(resp) + 1, unit) + resp)
    except (ConnectionResetError, OSError, TimeoutError):
        pass
    finally:
        conn.close()
        if served:
            print(f"[EBPro 断开] {peer}")


SIM_PROC = "FSimRun3.exe"


class _FILETIME(C.Structure):
    _fields_ = [("lo", C.c_ulong), ("hi", C.c_ulong)]


def proc_create_time(pid):
    """取进程创建时间（64 位 FILETIME），用于识别「PID 没变但仿真被重启」。"""
    try:
        k32 = C.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))   # QUERY_LIMITED_INFORMATION
        if not h:
            return 0
        try:
            ft = _FILETIME()
            ft_exit = _FILETIME()
            ft_kernel = _FILETIME()
            ft_user = _FILETIME()
            if not k32.GetProcessTimes(h, C.byref(ft), C.byref(ft_exit),
                                       C.byref(ft_kernel), C.byref(ft_user)):
                return 0
            return (ft.hi << 32) | ft.lo
        finally:
            k32.CloseHandle(h)
    except Exception:
        return 0


def sim_proc_info():
    """返回 GX Simulator3 的 (进程号, 创建时间)；没在运行返回 None。

    创建时间一起取，是为了区分「同一个 PID 但仿真被重启」的情况。
    """
    try:
        # 不用 text=True：中文 Windows 的 tasklist 输出是 GBK，
        # 在 UTF-8 模式解释器里会抛 UnicodeDecodeError（线程里异常还会被吞掉）。
        # 这里直接拿 bytes，按 UTF-8 宽容解码——进程名是 ASCII，不会误判。
        out = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {SIM_PROC}", "/FO", "CSV", "/NH"],
            capture_output=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        return None
    text = (out.stdout or b"").decode("utf-8", errors="replace")
    for line in text.splitlines():
        if SIM_PROC.lower() not in line.lower():
            continue
        parts = [p.strip().strip('"') for p in line.split('","')]
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        return (pid, proc_create_time(pid))
    return None


def sim_pid():
    """兼容旧接口：只取 PID。"""
    info = sim_proc_info()
    return info[0] if info else None


# GUI 与桥约定：GUI 写这个文件 = 请求「立即重新连接 GX 仿真」。
# 用完即删，纯本地文件信号，不需要额外端口或 socket。
LINK_REQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "link.req")
LINK_TAG = "__MXSTATE__"       # stdout 上的状态上报前缀，GUI 解析它更新状态灯
# 注意不要和 GUI 轮询队列里的 "__LINK__" 标记重名，两者是完全不同的通道。


def emit_link(up):
    """把 MX 会话的真实状态上报给 GUI（只在状态变化时调用，不刷屏）。"""
    print(f"{LINK_TAG}{'UP' if up else 'DOWN'}", flush=True)


def consume_link_req():
    """消费一次 GUI 发来的重连请求（刷新按钮 / GUI 兜底）。"""
    try:
        if os.path.exists(LINK_REQ):
            os.remove(LINK_REQ)
            return True
    except OSError:
        pass
    return False


def link_watchdog(worker, mx, interval=1.0):
    """持续保证「桥 ⇄ GX 仿真」的 MX 会话可用。

    1.0.4 的做法：
      • 每轮查 FSimRun3.exe（PID + 创建时间）。仿真启动/重启 → 作废旧会话，
        等约 2 秒让它完成初始化，再用**全新的 ActUtlType 实例**连接；
      • 仿真停止 → 立即作废会话、上报 DOWN，Modbus 502 继续监听；
      • 会话健康探测连续 3 次失败 → 新建实例重连；
      • Open 成功后必须回读 D0 校验，校验通过才 emit UP（杜绝「假绿」）；
      • GUI 的 link.req（⟳ 刷新）随时强制一次重连。

    重连只重建 COM 会话，Modbus TCP 监听与 EBPro 连接全程不断。
    """
    up = bool(getattr(mx, "connected", False))
    emit_link(up)
    print("[链路] 监视已启动：" + ("已连接 GX 仿真" if up else "等待 GX 仿真启动（会自动连接）"),
          flush=True)
    miss = 0                # 健康探测连续失败次数
    tries = 0               # 未连接状态下的重连尝试计数（用于退避）
    next_try = 0.0          # 下一次允许重连的时间点（time.time）
    sim_prev = sim_proc_info()

    while True:
        time.sleep(interval)
        now = time.time()
        force = consume_link_req()
        if force:
            print("[链路] 收到重连请求，正在重新连接 GX 仿真 …", flush=True)

        # ---- 1) 仿真进程实时检测 ----
        sim = sim_proc_info()
        if sim != sim_prev:
            if sim is None:
                print("[仿真] GX Simulator3 已停止，桥继续监听 502；"
                      "重新启动仿真后会自动连接", flush=True)
                if up:
                    up = False
                    emit_link(False)
                try:
                    worker.call(mx.invalidate, timeout=3.0)
                except Exception:
                    pass
                miss = 0
                tries = 0
                next_try = now + 10.0       # 仿真没跑时低频兜底重试
            else:
                print(f"[仿真] 检测到 GX Simulator3 已启动（PID {sim[0]}），"
                      "等待仿真就绪后自动连接 …", flush=True)
                if up:
                    up = False
                    emit_link(False)
                miss = 0
                tries = 0
                next_try = now + 2.0        # 给仿真器留初始化时间，别太早点 Open
            sim_prev = sim

        # ---- 2) 已连接时做健康探测 ----
        if up and not force:
            try:
                healthy = bool(worker.call(mx.probe, timeout=2.5))
            except Exception:
                healthy = False
            if healthy:
                miss = 0
                continue
            miss += 1
            if miss < 3:                    # 连续 3 次失败才判掉线，抗瞬时抖动
                continue
            up = False
            emit_link(False)
            print("[链路] 连续探测失败，MX 会话已失效，准备重新连接 …", flush=True)
            miss = 0
            next_try = now

        if force:
            if up:
                up = False
            # 手动刷新时无论原来是否已连接，都回报一次当前状态，
            # 这样 GUI 的「正在重新连接…」能立刻落回「等待/已连接」，不会一直悬着。
            emit_link(up)
            next_try = 0.0                  # 手动刷新：不等退避，立刻重连

        if now < next_try:
            continue

        # ---- 3) 新建实例重连 ----
        tries += 1
        try:
            ok = bool(worker.call(mx.reconnect, timeout=10.0))
        except Exception as e:
            ok = False
            print(f"[链路] 重连异常：{e}", flush=True)

        if ok:
            if not up:
                up = True
                emit_link(True)
                print("[链路] ✓ 已连接 GX 仿真（无需断开桥）", flush=True)
            tries = 0
            miss = 0
            next_try = now + interval
        else:
            if up:
                up = False
                emit_link(False)
            # 退避：仿真不存在时慢一点；存在但没就绪时先快后慢
            if sim is None:
                next_try = now + 10.0
            elif tries <= 2:
                next_try = now + 0.8
            elif tries <= 5:
                next_try = now + 2.0
            else:
                next_try = now + 4.0
            # 只在第一轮给一句提示，之后静默重试，不刷日志
            if tries == 1:
                print(f"[链路] 仿真尚未就绪（rc={rc_text(mx.last_rc)}），"
                      "稍后自动重试 …", flush=True)


class _SafeOut:
    """stdout 指向 GUI 管道。GUI 被强杀后管道会断，这时候任何 print 都会抛异常，
    把 Modbus 连接一起带崩 —— 所以统一吞掉写失败。"""

    def __init__(self, raw):
        self._raw = raw

    def write(self, text):
        try:
            return self._raw.write(text)
        except Exception:
            return len(text)

    def flush(self):
        try:
            self._raw.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    def __getattr__(self, name):
        return getattr(self._raw, name)


def pid_alive(pid):
    """判断进程是否还活着（不带管理员权限，读 SYNCHRONIZE 句柄即可）。"""
    if not pid:
        return False
    try:
        k32 = C.windll.kernel32
        h = k32.OpenProcess(0x00100000, False, int(pid))   # SYNCHRONIZE
        if not h:
            return False
        try:
            return k32.WaitForSingleObject(h, 0) == 0x102    # WAIT_TIMEOUT = 还活着
        finally:
            k32.CloseHandle(h)
    except Exception:
        return False


def watch_parent(ppid):
    """主程序（Catact.exe）被关掉或被任务管理器结束后，桥自己退出，避免残留进程占着 502。"""
    if not ppid:
        return
    while True:
        time.sleep(1.0)
        if not pid_alive(ppid):
            try:
                print("[桥] 主程序已退出，桥自动结束", flush=True)
            except Exception:
                pass          # 父进程没了，stdout 管道已断，打印失败不影响退出
            os._exit(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--station", type=int, default=1)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--tlb", default=None)
    ap.add_argument("--parent-pid", type=int, default=0,
                    help="GUI 进程号；主程序退出后桥自动结束（防止残留占端口）")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    try:
        sys.stdout = _SafeOut(sys.stdout)
        sys.stderr = _SafeOut(sys.stderr)
    except Exception:
        pass

    print(f"Python {sys.version.split()[0]} ({struct.calcsize('P') * 8} 位)")
    try:
        open(LOG_PATH, "w", encoding="utf-8").close()
    except Exception:
        pass

    # 看门狗要在连 MX 之前就开，否则 MX 连不上卡在重试时，家长已经没了桥还在
    threading.Thread(target=watch_parent, args=(args.parent_pid,), daemon=True).start()

    # 启动前清掉上一次遗留的重连请求，避免刚启动就做一次无谓重连
    consume_link_req()

    # 仿真器可能还没 RUN：Mx() 现在不再因此抛异常，桥照常监听 502，
    # 由 link_watchdog 在仿真启动后自动连上（不用再手动断开桥再开）。
    mx = Mx(args.station, args.tlb)
    print(f"[MX] 逻辑站号 {args.station} · " + ("已连接" if mx.connected else "等待仿真启动"),
          flush=True)

    w = Worker(mx)
    w.start()
    plc = Plc(w)
    threading.Thread(target=link_watchdog, args=(w, mx), daemon=True).start()

    if args.selftest:
        print("设备扫描：每个软元件读第 1 个点，看仿真器是否支持")
        ok, bad = [], []
        for dev in ("M", "X", "Y", "T", "C", "L", "S", "B", "SM", "F", "ST",
                    "D", "W", "SD", "ZR", "Z"):
            name = devname(dev, 0)
            try:
                vals, rc = mx.read_block(name, 1)
                if rc == 0:
                    ok.append(name)
                    print(f"  {name:<6} rc=0    值={vals[0]}")
                else:
                    bad.append(f"{name}(rc={rc})")
                    print(f"  {name:<6} rc={rc}  不支持")
            except Exception as e:
                bad.append(f"{name}(异常)")
                print(f"  {name:<6} 异常：{e}")
        print()
        print("支持  ：", "、".join(ok) if ok else "无")
        print("不支持：", "、".join(bad) if bad else "无")
        w.stop()
        mx.close()
        return

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((args.host, args.port))
    except OSError as e:
        print(f"绑定 {args.host}:{args.port} 失败：{e}")
        print("被占用的话换端口： --port 1502，EBPro 那边同步改。")
        return
    srv.listen(8)

    print(f"[桥] Modbus TCP 已启动 {args.host}:{args.port}")
    print("[桥] 0x 线圈   → M/S/B 读写；10001 起为 X/Y/L/SM/F/ST 可写镜像")
    print("[桥] 1x 离散   → X/Y/T/C/L/SM/F 只读；开关绑 1x 时桥会提示改 0x 地址")
    print("[桥] 4x 寄存器 → D/W/T当前/C当前…，FC06/FC16 均可写")
    print("[桥] 每次写入都会打印 [写入]/[写入未生效]/[写拒绝]，可据此定位按钮问题")

    try:
        while True:
            conn, peer = srv.accept()
            threading.Thread(target=client_worker, args=(conn, peer, plc), daemon=True).start()
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()
        w.stop()
        mx.close()
        print("\n已退出")


if __name__ == "__main__":
    main()
