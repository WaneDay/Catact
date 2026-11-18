# -*- coding: utf-8 -*-
"""Catact 离线自测（不需要 GX 仿真器 / MX Component / EBPro）

跑法：
    py -3 MXBridgeTool\\tests\\test_offline.py

覆盖：
  * 地址换算（桥、GUI 两张表必须一致）
  * FC05 / FC06 / FC0F / FC10 的写入路由与响应
  * 1x 兼容写入（旧 HMI 工程不改地址也能按）
  * FC16 数据偏移（历史 bug：单个寄存器会抛 struct.error）
  * SetDevice 返回码非 0 必须报错，不能假成功
  * 写入未生效（软元件不可写 / 被梯形图覆盖）的诊断日志
  * v1.0.4：启动/停止/刷新按钮互斥状态机
  * v1.0.4：重连必须新建 ActUtlType 实例并回读校验，不许假成功
  * v1.0.4：仿真进程签名（PID + 创建时间）读取不抛异常
"""

import os
import struct
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")

# mx_bridge 在导入时会 import comtypes 并加载 oleaut32，这里先 stub 掉 COM
sys.modules.setdefault("comtypes", types.ModuleType("comtypes"))
fake_client = types.ModuleType("comtypes.client")
fake_client.GetModule = lambda *a, **k: None
fake_client.CreateObject = lambda *a, **k: None
sys.modules["comtypes.client"] = fake_client

sys.path.insert(0, APP)
import mx_bridge as mb          # noqa: E402
import main as gui              # noqa: E402


LOG = os.path.join(tempfile.gettempdir(), "catact_test_bridge.log")
mb.LOG_PATH = LOG


def read_log():
    try:
        with open(LOG, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


class StubPlc:
    """记录写入；可模拟「写成功但不生效」和「写入被拒绝」"""

    def __init__(self):
        self.writes = []
        self.state = {}
        self.stuck = set()      # 写返回成功但值不保持（类似仿真器不认写 X）
        self.reject = set()     # SetDevice 返回错误

    def read_bits(self, dev, index, qty):
        return [self.state.get((dev, index + i), 0) for i in range(qty)]

    def read_words(self, dev, index, qty):
        return [self.state.get((dev, index + i), 0) for i in range(qty)]

    def write_bits(self, dev, index, values, verify=True):
        for i, v in enumerate(values):
            key = (dev, index + i)
            if key in self.reject:
                raise RuntimeError(f"{dev}{index + i} 写入返回 rc=0x00000001")
            self.writes.append((dev, index + i, 1 if v else 0))
            if key not in self.stuck:
                self.state[key] = 1 if v else 0
        if not verify:
            return None
        return [self.state.get((dev, index + i), 0) for i in range(len(values))]

    def write_words(self, dev, index, values, verify=True):
        for i, v in enumerate(values):
            key = (dev, index + i)
            if key in self.reject:
                raise RuntimeError(f"{dev}{index + i} 写入返回 rc=0x00000001")
            self.writes.append((dev, index + i, v))
            if key not in self.stuck:
                self.state[key] = v
        if not verify:
            return None
        return [self.state.get((dev, index + i), 0) for i in range(len(values))]


def fc05(addr, on=True):
    return struct.pack(">BHH", 0x05, addr, 0xFF00 if on else 0x0000)


def fc06(addr, val):
    return struct.pack(">BHH", 0x06, addr, val)


def fc15(addr, bits):
    data = bytearray((len(bits) + 7) // 8)
    for i, b in enumerate(bits):
        if b:
            data[i // 8] |= 1 << (i % 8)
    return struct.pack(">BHHB", 0x0F, addr, len(bits), len(data)) + bytes(data)


def fc16(addr, words):
    data = b"".join(struct.pack(">H", w) for w in words)
    return struct.pack(">BHHB", 0x10, addr, len(words), len(data)) + data


class TestMap(unittest.TestCase):
    def test_bridge_resolve(self):
        self.assertEqual(mb.resolve("0x", 0), ("M", 0))
        self.assertEqual(mb.resolve("0x", 10000), ("X", 0))
        self.assertEqual(mb.resolve("0x", 11008), ("Y", 8))
        self.assertEqual(mb.resolve("1x", 1008), ("Y", 8))
        self.assertEqual(mb.resolve("1x", 0), ("X", 0))
        self.assertEqual(mb.resolve("4x", 0), ("D", 0))

    def test_devname_radix(self):
        self.assertEqual(mb.devname("Y", 8), "Y10")
        self.assertEqual(mb.devname("X", 9), "X11")
        self.assertEqual(mb.devname("B", 31), "B1F")
        self.assertEqual(mb.devname("M", 10), "M10")

    def test_gui_map_matches_bridge(self):
        self.assertEqual(gui.AddrMap.name_to_addr("X0"), (("0x", 10001), None))
        self.assertEqual(gui.AddrMap.name_to_addr("X1"), (("0x", 10002), None))
        self.assertEqual(gui.AddrMap.name_to_addr("Y10"), (("0x", 11009), None))
        self.assertEqual(gui.AddrMap.name_to_addr("M0"), (("0x", 1), None))
        self.assertEqual(gui.AddrMap.name_to_addr("D100"), (("4x", 101), None))
        self.assertEqual(gui.AddrMap.name_to_addr("W1F"), (("4x", 8032), None))
        self.assertEqual(gui.AddrMap.name_to_addr("T5"), (("1x", 2006), None))
        self.assertEqual(gui.AddrMap.name_to_addr("T5.V"), (("4x", 9006), None))
        self.assertEqual(gui.AddrMap.mirror_addr("1x", 1009), 11009)
        self.assertEqual(gui.AddrMap.addr_to_name("0x", 10001), ("X0", None))

    def test_gui_x_y_monitor_is_writable(self):
        for text, area, dev, start, cnt in gui.AddrMap.BAR:
            if dev in ("X", "Y"):
                self.assertEqual(area, "0x", dev)
                seg = gui.AddrMap.segment(area, dev)
                self.assertGreater(seg[0], 10000)


class TestWrites(unittest.TestCase):
    def setUp(self):
        with open(LOG, "w", encoding="utf-8"):
            pass

    def test_fc05_mirror_x0(self):
        plc = StubPlc()
        pdu = fc05(10000)
        self.assertEqual(mb.handle_pdu(pdu, plc), pdu)
        self.assertEqual(plc.writes, [("X", 0, 1)])
        self.assertIn("[写入] 0x 10001 → X0=1", read_log())

    def test_fc05_y10(self):
        plc = StubPlc()
        pdu = fc05(11008, False)
        self.assertEqual(mb.handle_pdu(pdu, plc), pdu)
        self.assertEqual(plc.writes, [("Y", 8, 0)])

    def test_fc05_address_mismatch_hint(self):
        """旧 HMI 绑 1x 时，FC05 会落到同号的 M/S/B；必须提示用户改地址"""
        plc = StubPlc()
        mb.handle_pdu(struct.pack(">BHH", 2, 0, 1), plc)   # HMI 读 1x 1（X0）
        with open(LOG, "w", encoding="utf-8"):
            pass
        pdu = fc05(0)                                      # 写 FC05 addr 0 → M0
        self.assertEqual(mb.handle_pdu(pdu, plc), pdu)
        self.assertEqual(plc.writes, [("M", 0, 1)])
        log = read_log()
        self.assertIn("[写入] 0x 1 → M0=1", log)
        self.assertIn("[地址提示]", log)
        self.assertIn("1x 1（X0）", log)
        self.assertIn("0x 10001", log)

    def test_fc05_mismatch_hint_y10(self):
        plc = StubPlc()
        mb.handle_pdu(struct.pack(">BHH", 2, 1008, 1), plc)  # 读 1x 1009（Y10）
        with open(LOG, "w", encoding="utf-8"):
            pass
        mb.handle_pdu(fc05(1008), plc)                        # 写 0x 1009（B8）
        log = read_log()
        self.assertIn("1x 1009（Y10）", log)
        self.assertIn("0x 11009", log)

    def test_fc05_out_of_table_rejected_and_logged(self):
        plc = StubPlc()
        resp = mb.handle_pdu(fc05(19999), plc)
        self.assertEqual(resp[:1], b"\x85")
        self.assertEqual(resp[1], 0x02)
        self.assertEqual(plc.writes, [])
        self.assertIn("[写拒绝]", read_log())

    def test_fc05_bad_value_rejected(self):
        plc = StubPlc()
        resp = mb.handle_pdu(struct.pack(">BHH", 5, 0, 0x1234), plc)
        self.assertEqual(resp[1], 0x03)

    def test_fc05_write_not_effective_is_reported(self):
        plc = StubPlc()
        plc.stuck.add(("X", 0))    # 写返回成功但值不保持
        pdu = fc05(10000)
        self.assertEqual(mb.handle_pdu(pdu, plc), pdu)
        log = read_log()
        self.assertIn("[写入未生效]", log)
        self.assertIn("X0=1", log)

    def test_fc05_mx_error_returns_04(self):
        plc = StubPlc()
        plc.reject.add(("X", 0))
        resp = mb.handle_pdu(fc05(10000), plc)
        self.assertEqual(resp[1], 0x04)
        self.assertIn("[写失败]", read_log())

    def test_fc06_word(self):
        plc = StubPlc()
        pdu = fc06(100, 1234)      # D100
        self.assertEqual(mb.handle_pdu(pdu, plc), pdu)
        self.assertEqual(plc.writes, [("D", 100, 1234)])

    def test_fc15_multi_bits(self):
        plc = StubPlc()
        pdu = fc15(10000, [1, 0, 1])
        self.assertEqual(mb.handle_pdu(pdu, plc), bytes([0x0F]) + pdu[1:5])
        self.assertEqual(plc.writes, [("X", 0, 1), ("X", 1, 0), ("X", 2, 1)])

    def test_fc16_single_register_old_bug(self):
        """历史 bug：数据从 pdu[7] 起读，单个寄存器直接 struct.error"""
        plc = StubPlc()
        pdu = fc16(100, [0x1234])   # D100 = 0x1234
        resp = mb.handle_pdu(pdu, plc)
        self.assertEqual(resp, bytes([0x10]) + pdu[1:5])
        self.assertEqual(plc.writes, [("D", 100, 0x1234)])

    def test_fc16_multi_registers(self):
        plc = StubPlc()
        mb.handle_pdu(fc16(9000, [11, 22, 33]), plc)   # T current 9001 起
        self.assertEqual(plc.writes, [("T", 0, 11), ("T", 1, 22), ("T", 2, 33)])

    def test_fc16_malformed_rejected(self):
        plc = StubPlc()
        bad = struct.pack(">BHHB", 0x10, 0, 2, 2) + b"\x00\x01"   # 字节数应为 4
        self.assertEqual(mb.handle_pdu(bad, plc)[1], 0x03)

    def test_fc16_out_of_table(self):
        plc = StubPlc()
        resp = mb.handle_pdu(fc16(31000, [1]), plc)     # 显示 31001，超出 4x 表
        self.assertEqual(resp[1], 0x02)
        self.assertEqual(plc.writes, [])


class FakeMx:
    def __init__(self, rc):
        self.rc = rc

    def set(self, dev, value):
        return self.rc


class FakeWorker:
    def __init__(self, mx):
        self.mx = mx

    def call(self, fn, *args, **kwargs):
        return fn(*args)


class TestSetDeviceRc(unittest.TestCase):
    def test_rc_zero_is_ok(self):
        plc = mb.Plc(FakeWorker(FakeMx(0)))
        self.assertIsNone(plc.write_bits("X", 0, [1], verify=False))

    def test_rc_nonzero_raises(self):
        plc = mb.Plc(FakeWorker(FakeMx(0xF1000020)))
        with self.assertRaises(RuntimeError) as ctx:
            plc.write_bits("X", 0, [1], verify=False)
        self.assertIn("F1000020", str(ctx.exception))


class TestButtonStates(unittest.TestCase):
    """v1.0.4：启动/停止/刷新三键必须严格互斥，且停止后启动能恢复。"""

    def test_idle(self):
        self.assertEqual(gui.button_states(False),
                         {"start": "normal", "stop": "disabled", "refresh": "disabled"})

    def test_running(self):
        self.assertEqual(gui.button_states(True),
                         {"start": "disabled", "stop": "normal", "refresh": "normal"})

    def test_starting(self):
        self.assertEqual(gui.button_states(False, True),
                         {"start": "disabled", "stop": "disabled", "refresh": "disabled"})

    def test_start_recovers_after_stop(self):
        """旧版停止后启动键永远灰着（只能走菜单），这里必须恢复 normal。"""
        self.assertEqual(gui.button_states(False)["start"], "normal")

    def test_no_state_self_latching_in_source(self):
        src = open(os.path.join(APP, "main.py"), encoding="utf-8").read()
        self.assertNotIn('self.btn_start["state"] != "normal"', src)


class FakeBridgeMx(mb.Mx):
    """只测重连决策，不碰真实 COM。基类 __init__ 不执行。"""

    def __init__(self, healthy=True):
        self.station = 1
        self.connected = False
        self.last_rc = None
        self.act = object()
        self.pdisp = None
        self.invoke = None
        self.healthy = healthy
        self.made = 0
        self.dropped = 0
        self.opened = 0

    def _drop_session(self):
        self.dropped += 1
        self.act = None
        self.connected = False

    def _make(self):
        self.made += 1
        self.act = object()

    def _open(self, tries=1, gap=0.0):
        self.opened += 1
        self.connected = True
        return True

    def verify(self, tries=2, gap=0.25):
        return self.healthy


class TestMxReconnect(unittest.TestCase):
    """v1.0.4：重连必须新建实例，并且 Open 后回读校验通过才算连上。"""

    def test_reconnect_builds_new_object(self):
        mx = FakeBridgeMx(healthy=True)
        self.assertTrue(mx.reconnect())
        self.assertEqual(mx.dropped, 1, "必须先丢弃旧会话")
        self.assertEqual(mx.made, 1, "必须新建 ActUtlType 实例")
        self.assertEqual(mx.opened, 1)
        self.assertTrue(mx.connected)

    def test_open_ok_but_read_fails_is_down(self):
        mx = FakeBridgeMx(healthy=False)
        self.assertFalse(mx.reconnect(), "Open 成功但读不到数据，不能上报已连接")
        self.assertFalse(mx.connected)

    def test_invalidate_releases_session(self):
        mx = FakeBridgeMx()
        mx.connected = True
        mx.invalidate()
        self.assertIsNone(mx.act)
        self.assertFalse(mx.connected)


class TestRcText(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(mb.rc_text(0xF0000004), "0xF0000004")
        self.assertEqual(mb.rc_text(0), "0x00000000")
        self.assertEqual(mb.rc_text(None), "未知")
        self.assertEqual(mb.rc_text("异常：x"), "异常：x")


class TestSimProc(unittest.TestCase):
    def test_signature_shape(self):
        """仿真没跑时返回 None；在跑时返回 (pid, 创建时间)。不能抛异常。"""
        info = mb.sim_proc_info()
        self.assertTrue(info is None or (isinstance(info, tuple) and len(info) == 2
                                         and isinstance(info[0], int)))


class TestBridgeProcParsing(unittest.TestCase):
    """端口被残留桥占住时，GUI 要能认出「这是上次残留的桥」还是「另一个 Catact 的桥」"""

    PS_OUT = (
        "100\t1\tCatact.exe\tD:\\cat\\Catact.exe\t\"Catact.exe\"\r\n"
        "101\t1\tpwsh.exe\tC:\\win\\pwsh.exe\t\"pwsh.exe\"\r\n"
        "200\t101\tpython.exe\tC:\\py\\python.exe\tpython.exe -u D:\\x\\mx_bridge.py --station 1 --port 502\r\n"
        "201\t200\tpython.exe\tC:\\py\\python.exe\tsomething else\r\n"
        "300\t100\tpython.exe\tC:\\py\\python.exe\tpython.exe -u D:\\cat\\mx_bridge.py --station 1 --port 502\r\n"
        "400\t99999\tpython.exe\tC:\\py\\python.exe\tpython.exe -u D:\\old\\mx_bridge.py --station 1 --port 502\r\n"
        "500\t1\tpython.exe\tC:\\py\\python.exe\tpython.exe -u D:\\x\\mx_bridge.py --station 1 --port 1502\r\n"
        "600\t1\tnotepad.exe\tC:\\win\\notepad.exe\tnotepad.exe mx_bridge.py --port 502\r\n"
        "garbage line\r\n"
    )

    def test_orphan_vs_other_instance(self):
        # 200 的父进程是 pwsh（手动跑的桥）→ 可清理；400 父进程已消失 → 可清理；
        # 300 的父进程是 Catact.exe → 另一个实例在用，不能动
        orphans, others = gui.classify_bridge_procs(gui.parse_proc_table(self.PS_OUT), 502)
        self.assertEqual([p["pid"] for p in orphans], [200, 400])
        self.assertEqual([p["pid"] for p in others], [300])

    def test_own_bridge_skipped(self):
        # 自己的桥：父进程就是本进程 100 → 不参与清理判断，交给 bridge.stop() 管
        orphans, others = gui.classify_bridge_procs(
            gui.parse_proc_table(self.PS_OUT), 502, self_pid=100)
        self.assertNotIn(300, [p["pid"] for p in orphans + others])

    def test_other_port_ignored(self):
        orphans, others = gui.classify_bridge_procs(gui.parse_proc_table(self.PS_OUT), 1502)
        self.assertEqual([p["pid"] for p in orphans], [500])
        self.assertEqual(others, [])

    def test_non_python_ignored(self):
        procs = gui.classify_bridge_procs(gui.parse_proc_table(self.PS_OUT), 502)
        for p in procs[0] + procs[1]:
            self.assertEqual(p["name"].lower(), "python.exe")

    def test_bridge_args_carry_parent_pid(self):
        """桥必须带 --parent-pid，主程序被杀后才能自己退出，不占着 502"""
        src = open(os.path.join(APP, "mx_bridge.py"), encoding="utf-8").read()
        self.assertIn("--parent-pid", src)
        self.assertIn("watch_parent", src)
        gui_src = open(os.path.join(APP, "main.py"), encoding="utf-8").read()
        self.assertIn('"--parent-pid"', gui_src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
