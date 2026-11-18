# -*- coding: utf-8 -*-
"""GUI 按钮状态机实测（真 tkinter，不连桥）

跑法：
    py -3 MXBridgeTool\\tests\\test_gui_state.py

只验证「按钮状态 / 颜色 / 光标」这套 UI 逻辑，不启动真实桥进程。
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)

import main as gui   # noqa: E402


class FakeProc:
    def __init__(self, alive):
        self.alive = alive

    def poll(self):
        return None if self.alive else 0


class TestGuiButtons(unittest.TestCase):
    def setUp(self):
        self.app = gui.App()
        self.app.withdraw()
        self.app.polling = False
        try:
            self.app.update_idletasks()
        except Exception:
            pass

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def states(self):
        a = self.app
        return (a.btn_start["state"], a.btn_stop["state"], a.btn_refresh["state"])

    def test_idle(self):
        self.app.bridge.proc = None
        self.app._refresh_buttons()
        self.assertEqual(self.states(), ("normal", "disabled", "disabled"))
        self.assertEqual(self.app.btn_start["bg"], gui.GREEN)
        self.assertEqual(self.app.btn_stop["bg"], gui.BG)

    def test_running(self):
        self.app.bridge.proc = FakeProc(True)
        self.app._refresh_buttons()
        self.assertEqual(self.states(), ("disabled", "normal", "normal"))
        self.assertEqual(self.app.btn_start["bg"], gui.BG)
        self.assertEqual(self.app.btn_stop["bg"], gui.RED)

    def test_after_stop_recovers(self):
        """点过启动再停止：启动键必须回到 normal，停止/刷新回到 disabled。"""
        self.app.bridge.proc = FakeProc(True)
        self.app._refresh_buttons()
        self.app.bridge.proc = FakeProc(False)
        self.app._refresh_buttons()
        self.assertEqual(self.states(), ("normal", "disabled", "disabled"))

    def test_disabled_is_visibly_grey(self):
        self.app.bridge.proc = None
        self.app._refresh_buttons()
        for btn in (self.app.btn_stop, self.app.btn_refresh):
            self.assertEqual(btn["bg"], gui.BG)
            self.assertEqual(btn["cursor"], "arrow")
            self.assertEqual(btn["fg"], "#808080")

    def test_refresh_busy_disables(self):
        self.app.bridge.proc = FakeProc(True)
        self.app._refresh_busy_until = float("inf")
        self.app._refresh_buttons()
        self.assertEqual(self.app.btn_refresh["state"], "disabled")
        self.app._refresh_busy_until = 0.0
        self.app._refresh_buttons()
        self.assertEqual(self.app.btn_refresh["state"], "normal")


if __name__ == "__main__":
    unittest.main(verbosity=2)
