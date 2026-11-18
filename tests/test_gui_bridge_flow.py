# -*- coding: utf-8 -*-
"""GUI ↔ 桥 端到端流程实测（不连 GX 仿真，只用 1502 端口）

跑法：
    py -3 MXBridgeTool\\tests\\test_gui_bridge_flow.py

验证：
  1. 未启动时：启动可点、停止/刷新不可点
  2. 点启动后：启动变灰、停止/刷新可点，日志出现「Modbus TCP 已启动」
  3. 点刷新后：日志出现「已请求重新连接」，按钮进入短暂忙状态
  4. 点停止后：启动恢复可点、停止/刷新变灰
"""
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)

import main as gui   # noqa: E402

TEST_PORT = 1502


class TestGuiBridgeFlow(unittest.TestCase):
    def setUp(self):
        self.app = gui.App()
        self.app.withdraw()
        self.app.cfg["port"] = TEST_PORT
        self.app.lbl_port.config(text=str(TEST_PORT))
        self.app.polling = False
        # 不弹监视窗口，避免测试时闪窗
        self.app.toggle_window = lambda dev: None
        self.pump(0.3)

    def tearDown(self):
        try:
            self.app.bridge.stop()
        except Exception:
            pass
        try:
            self.app.destroy()
        except Exception:
            pass

    def pump(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                self.app.update()
            except Exception:
                pass
            time.sleep(0.05)

    def states(self):
        return (self.app.btn_start["state"], self.app.btn_stop["state"],
                self.app.btn_refresh["state"])

    def logtext(self):
        try:
            return self.app.txt_log.get("1.0", "end")
        except Exception:
            return ""

    def test_full_flow(self):
        self.assertEqual(self.states(), ("normal", "disabled", "disabled"))

        self.app.start_bridge()
        self.pump(4.0)
        self.assertTrue(self.app.bridge.running, "桥进程没有起来")
        self.assertEqual(self.states(), ("disabled", "normal", "normal"))
        log = self.logtext()
        self.assertIn("桥已启动", log)
        self.assertIn("Modbus TCP 已启动 127.0.0.1:1502", log)
        # 本机若已开着 GX 仿真，桥会直接连上；两种状态都说明链路逻辑正常。
        if "未连接 GX 仿真" not in log:
            self.assertIn("已连接 GX 仿真", log,
                          "桥既没提示等待仿真，也没连上仿真")

        # 刷新：手动兜底应发信号并在按钮上进入忙状态
        self.app.refresh_link()
        self.assertEqual(self.app.btn_refresh["state"], "disabled")
        self.pump(2.5)
        self.assertIn("已请求重新连接 GX 仿真", self.logtext())
        self.assertTrue(self.app.bridge.running, "刷新不应停止桥进程")

        self.app.stop_bridge()
        self.pump(1.5)
        self.assertFalse(self.app.bridge.running)
        self.assertEqual(self.states(), ("normal", "disabled", "disabled"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
