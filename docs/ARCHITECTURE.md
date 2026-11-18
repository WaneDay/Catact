# 架构说明

## 进程模型

```
+---------------------------+
| Catact.exe (64-bit Tkinter)|
|  GUI / 监视窗口 / 按钮     |
+------------+--------------+
             | stdout: __MXSTATE__UP / DOWN
             | 同目录 link.req
             v
+---------------------------+
| python32\python.exe (32)   |
| mx_bridge.py               |
|  MX Component ActUtlType   |
|  Modbus TCP Server :502    |
+------------+--------------+
             | COM
             v
+---------------------------+
| GX Simulator3 (FX5U)       |
+---------------------------+
```

- GUI 不加载 COM，避免 64 位进程加载 32 位组件失败。
- 桥用 32 位 Python 跑，独占 MX Component。
- GUI 和桥通过子进程 stdout 和同目录 `link.req` 通信，不额外开控制端口。

## 桥的重连规则

1. `reconnect()` 丢弃旧 `ActUtlType`，新建实例再 `Open()`。
2. `Open()` 最多 3 次。
3. `verify()` 回读 D0，成功才算连上。
4. 只有 `reconnect()` 成功才向 GUI 发 `__MXSTATE__UP`。
5. `link_watchdog` 每秒检查 `FSimRun3.exe` 的 PID + 创建时间：
   - 签名变化（无→有 / 有→无 / 新进程）→ 作废旧会话，安排重连。
   - 已连接时连续 3 次 `probe()` 失败 → 判掉线，立即重连。
   - 收到 `link.req` → 立即重连。
6. 失败退避：仿真未启动 10 秒；刚试 1–2 次 0.8 秒；3–5 次 2 秒；更多 4 秒。

## Modbus 地址映射

| EBPro 区 | PLC 元件 | 说明 |
|---|---|---|
| `0x` 线圈 | M / S / B；X/Y 可写镜像 | 开关/按钮用这里 |
| `1x` 离散 | X / Y / T / C / L / SM / F | 只读 |
| `4x` 寄存器 | D / W / T 当前 / C 当前 | FC06 / FC16 可写 |

- `0x 1` = M0
- `0x 10001` = X0（可写镜像）
- `0x 11001` = Y0（可写镜像）
- `1x 1` = X0（只读）
- `1x 1001` = Y0（只读）
- `4x 1` = D0
- X/Y 八进制；W/B/SB/SW 十六进制；其余十进制。

**0x 与 1x 编号重叠但含义不同**，这是 EBPro 开关回弹的根因。开关必须绑 `0x`。

## GUI 按钮状态机

- 只按「桥进程是否在跑」判断：
  - 桥停：启动可点，停止/重连禁用（灰色、箭头光标）。
  - 桥跑：启动禁用，停止/重连可点。
- 不按按钮当前 `state` 反推，避免自锁。
- 桥状态与仿真状态分开显示；绿灯要求 `mx_up` 且 D0 回读成功。

## 语言

- 默认 `zh`；`config.json` 的 `lang` 可为 `zh` / `en`。
- `_TR` 双语表 + `T()` 取词；静态和动态状态都走 `T()`。
- 中文按 `Microsoft YaHei UI → Microsoft YaHei → SimSun → Segoe UI` 回退。
- 切换语言写配置后重启进程，确保所有 Tk 控件文字重建。

更完整的踩坑记录见 [`HANDOFF.md`](HANDOFF.md) 和 [`PROJECT_LOG.md`](PROJECT_LOG.md)。
