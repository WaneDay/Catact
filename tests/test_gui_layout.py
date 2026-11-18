# -*- coding: utf-8 -*-
"""Win7 经典 UI 布局回归（真 tkinter，不显示窗口）

跑法：
    py -3 MXBridgeTool\\tests\\test_gui_layout.py

检查：
  1. ttk 使用 classic 主题（不是 vista / 现代扁平）
  2. 顶层菜单是英文 File/Edit/View/Options/Help
  3. 工具栏、Device Monitor、五格状态栏的请求宽度不超过窗口宽度
"""
import os
import sys
import unittest
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)

import main as gui   # noqa: E402


class TestClassicLayout(unittest.TestCase):
    def setUp(self):
        self.app = gui.App()
        self.app.withdraw()
        self.app.polling = False
        self.app.update_idletasks()
        geom = self.app.geometry().split("+")[0]
        self.w, self.h = (int(x) for x in geom.split("x"))

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def test_theme_is_classic(self):
        self.assertEqual(ttk.Style(self.app).theme_use(), "classic")

    def test_menu_is_chinese_by_default(self):
        menu = self.app.nametowidget(self.app.cget("menu"))
        labels = [menu.entrycget(i, "label")
                  for i in range(menu.index("end") + 1)
                  if menu.type(i) != "tearoff"]
        self.assertEqual(labels[:5], ["文件", "编辑", "视图", "选项", "帮助"])

    def test_translation_switch(self):
        old = gui.LANG
        try:
            gui.LANG = "zh"
            self.assertEqual(gui.T("menu_file"), "文件")
            self.assertEqual(gui.T("tb_run"), "▶ 启动")
            gui.LANG = "en"
            self.assertEqual(gui.T("menu_file"), "File")
            self.assertEqual(gui.T("tb_run"), "▶ Run")
        finally:
            gui.LANG = old

    def test_chinese_font_is_cjk_capable(self):
        self.assertIn(gui.FONT[0], ("Microsoft YaHei UI", "Microsoft YaHei",
                                    "SimSun", "Segoe UI"))

    def test_change_language_saves_and_restarts(self):
        from unittest import mock
        with mock.patch("main.messagebox.askyesno", return_value=True), \
             mock.patch.object(self.app, "save_cfg") as save, \
             mock.patch.object(self.app, "restart_app") as restart:
            self.app.change_language("en")
        self.assertEqual(self.app.cfg["lang"], "en")
        save.assert_called_once()
        restart.assert_called_once()

    def test_change_language_aborts_when_config_not_writable(self):
        from unittest import mock
        with mock.patch("main.messagebox.askyesno", return_value=True), \
             mock.patch.object(self.app, "save_cfg", return_value=False), \
             mock.patch("main.messagebox.showerror") as err, \
             mock.patch.object(self.app, "restart_app") as restart:
            self.app.change_language("en")
        self.assertEqual(self.app.cfg["lang"], "zh")
        restart.assert_not_called()
        err.assert_called_once()

    def test_toolbar_fits(self):
        tb = self.app.btn_start.master
        req = sum(w.winfo_reqwidth() for w in tb.winfo_children())
        self.assertLess(req, self.w, "工具栏比窗口宽")

    def test_device_bar_fits(self):
        db = self.app.dev_btns["M"].master
        req = sum(w.winfo_reqwidth() + 2 for w in db.winfo_children())
        # 右侧画布 = 窗口 - 左侧树（约 220）
        self.assertLess(req, self.w - 220, "Device Monitor 按钮条溢出")

    def test_status_bar_fits(self):
        sb = self.app.lbl_st_bridge.master
        req = sum(w.winfo_reqwidth() for w in sb.winfo_children())
        self.assertLess(req, self.w, "状态栏五格溢出")

    def test_device_buttons_are_classic_buttons(self):
        b = self.app.dev_btns["M"]
        self.assertEqual(b.winfo_class(), "Button")
        self.assertEqual(b.cget("relief"), "raised")
        self.assertEqual(int(b.cget("bd")), 2)

    def test_tree_has_project_root(self):
        roots = self.app.tree.get_children("")
        self.assertTrue(roots)
        self.assertEqual(self.app.tree.item(roots[0], "text"), "Catact 工程")

    def test_monitor_cell_is_sunken(self):
        self.app.toggle_window("M")
        win = self.app.windows["M"]
        self.assertEqual(win.cells[0].cget("relief"), "sunken")
        self.assertEqual(int(win.cells[0].cget("bd")), 1)
        win.close()

    def test_mx_group_present(self):
        self.app._update_mx_state(force=True)
        self.assertEqual(self.app.btn_mx_open.cget("text"), "打开 MX 工具")
        grp = self.app.btn_mx_open.master.master
        self.assertLess(grp.winfo_reqwidth(), self.w - 220,
                        "MX Environment 分组框溢出")

    def test_open_mx_utility_uses_popen(self):
        import sys
        from unittest import mock
        self.app.cfg["mx_utility"] = sys.executable
        self.app._mx_util_cache = sys.executable
        with mock.patch("main.subprocess.Popen") as pop:
            self.app.open_mx_utility()
        pop.assert_called_once()
        self.assertEqual(pop.call_args[0][0], [sys.executable])


if __name__ == "__main__":
    unittest.main(verbosity=2)
