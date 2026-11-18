# -*- coding: utf-8 -*-
"""MX 现场诊断（只读，不写 PLC）——用内置 32 位 Python 跑：

    MXBridgeTool\\app\\python32\\python.exe tests\\diag_mx.py

作用：
  1) 打印 Open() 的返回码；
  2) 读 D0 / M0 / X0 / Y0，打印 rc 与值；
  3) 连续跑 N 轮（默认 5 轮，间隔 2 秒），观察 GX 仿真「启动/停止」时
     rc 的变化规律，用来判断「会话失效」到底表现为 rc≠0 还是 rc=0 但全 0。

注意：本脚本只读，不 SetDevice。可在 GX 仿真停止/运行两种状态下分别跑，
     把输出贴到日志里对比。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "app")
sys.path.insert(0, APP)

import mx_bridge as mb   # noqa: E402


def one_round(mx, tag):
    print(f"\n--- {tag} ---")
    t0 = time.time()
    rc_open = None
    try:
        rc_open = mx.act.Open()
    except Exception as e:
        print(f"Open 异常：{e}")
    print(f"Open() rc={rc_open}")
    for dev, size in (("D0", 1), ("M0", 16), ("X0", 16), ("Y0", 16), ("SD0", 1)):
        try:
            vals, rc = mx.read_block(dev, size)
            print(f"read {dev:<4} rc={rc}  值={vals[:8]}")
        except Exception as e:
            print(f"read {dev:<4} 异常：{e}")
    print(f"用时 {time.time() - t0:.2f}s")


def main():
    station = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    gap = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0

    print(f"解释器位数：{'64 位' if sys.maxsize > 2**32 else '32 位'}")
    print(f"TLB：{mb.find_tlb()}")
    try:
        mx = mb.Mx(station)
    except Exception as e:
        print(f"创建 ActUtlType 失败：{e}")
        return
    for i in range(rounds):
        one_round(mx, f"第 {i + 1}/{rounds} 轮")
        if i + 1 < rounds:
            time.sleep(gap)

    print("\n--- 重建会话（等价于把桥关掉再打开）---")
    ok = mx.reconnect()
    print(f"reconnect() = {ok}  last_rc={mb.rc_text(mx.last_rc)}")
    try:
        mx.close()
    except Exception:
        pass


if __name__ == "__main__":
    main()
