# Catact 项目日志（交接 / 维护用）

> 项目：Catact —— GX Works3 FX5U 仿真器 ⇄ 威纶通 EBPro 的 Modbus TCP 桥
> 当前版本：**v1.0.6**（2026-11-18）
> 位置：`D:\Project folder\删掉\91\软件制作文件夹`
> 本文目的：记录项目构成、运行逻辑、1.0.0 → 1.0.6 的修复史，以及以后改代码 / 重打包的标准流程。遇到同类问题先查本文末尾的「调试速查」。

---

## 一、这个软件是干什么的

威纶通 EBPro 组态好的 HMI 画面，正常要连真实 PLC 才能跑。毕设阶段没有 FX5U 实机，只有 GX Works3 自带的 **GX Simulator3** 仿真器；而 EBPro 只会说 Modbus TCP，不会说三菱的 MX Component 协议。

Catact 做的就是中间这层翻译：

```
EBPro (Modbus TCP 主站)
        │  127.0.0.1:502，站号 1
        ▼
Catact 桥（32 位 Python，mx_bridge.py）
        │  MX Component ActUtlType（COM，只能 32 位）
        ▼
GX Simulator3（GX Works3 的 FX5U 软 PLC）
```

目标：没有真实 PLC，也能在 EBPro 里点按钮、看指示灯、改 D 寄存器，改动实时反映到 GX 仿真器的软元件里。

---

## 二、目录构成

### 1. 交付目录（给用户 / 评测用）

```
D:\Project folder\删掉\91\软件制作文件夹\
├─ 0_先看这里.txt                  入口说明
├─ 1_Catact交接报告.md             上一手写的完整交接（39KB，架构/地址表/坑）
├─ 2_Catact_1.0.6_免安装版.zip      ★ 最新交付（解压即用）
├─ 2_Catact_1.0.6_免安装版\Catact\  ★ 解压后的目录
├─ 3_Catact_1.0.6_安装包.exe        安装版（Inno Setup，可选）
├─ 4_用户使用说明.txt              面向用户的操作说明
├─ 5_交接提示词.txt                 上一手给 AI 的交接提示词（含重打包顺序）
├─ 6_本次修复说明.txt               v1.0.2 的修复说明
├─ 7_修复参考_跨段拆分.md           FC16 跨段写入的参考
├─ 8_Catact_1.0.4_修复说明.txt      1.0.4 修复说明（按钮状态机 / 自动重连）
├─ 9_Catact项目日志.md              ★ 本文
├─ 10_Catact_1.0.5_UI改版说明.txt   1.0.5 UI 改版说明
├─ 11_Catact_1.0.6_语言设置说明.txt ★ 本轮语言设置说明（先看这个）
├─ _diff_100_101.txt                1.0.0→1.0.1 源码 diff
├─ _diff_main_102_103.txt           1.0.2→1.0.3 源码 diff
├─ _ver_100.py / _ver_101.py / _ver_102.py   历史版本快照
├─ 备份_修改前_v1.0.3_20261118_1835\          1.0.4 改前快照
├─ 备份_修改前_v1.0.4_20261118_1905\          1.0.5 改前快照（含 1.0.4 成品与源码）
└─ 备份_修改前_v1.0.5_20261118_2235\          ★ 1.0.6 改前快照（1.0.5 成品）
```

### 2. 源码工程 `MXBridgeTool\`

```
MXBridgeTool\
├─ app\
│  ├─ main.py              GUI（64 位 Python / PyInstaller 打包成 Catact.exe）
│  ├─ mx_bridge.py         桥（必须用 32 位 Python 跑）
│  ├─ python32\            32 位便携 Python 3.12 + comtypes
│  ├─ catact.ico           图标
│  └─ modbus_debug.log     桥的运行日志（运行时生成，打包时排除）
├─ tests\
│  ├─ test_offline.py      离线单元测试（协议 / 地址 / 按钮状态机 / 重连）
│  ├─ test_gui_state.py    tkinter 按钮状态实测（不需要桥）
│  ├─ test_gui_layout.py   Win7 风格 / 布局 / 双语 / 字体 / MX 分组
│  ├─ test_gui_bridge_flow.py  GUI ↔ 桥 端到端（1502 端口）
│  └─ diag_mx.py           MX 只读诊断（用 python32 跑）
├─ release\Catact\         打包工作目录（Catact.exe + mx_bridge.py + python32…）
├─ build_release.py        一键打包：测试 → PyInstaller → Inno → zip
├─ Catact.iss              Inno Setup 脚本
├─ README.txt              随包说明（会被复制进 release）
└─ dist\                   PyInstaller 输出
```

### 3. 运行时生成的文件（与 `mx_bridge.py` 同目录）

| 文件 | 作用 |
|---|---|
| `config.json` | GUI 设置：端口、站号、窗口位置等 |
| `modbus_debug.log` | 桥的写入 / 错误日志（排查按钮问题的第一手材料） |
| `link.req` | GUI → 桥的「请重连」信号文件，桥读到即删（v1.0.3 引入） |

---

## 三、为什么要两个进程

`MX Component` 的 `ActUtlType` 是 **32 位 COM 组件**，64 位进程加载不了；而现代 Python / PyInstaller 默认 64 位，GUI 用 64 位更稳。于是拆成：

- **GUI（64 位，Catact.exe）**：只负责界面、按钮、监视窗口、发信号；不碰 COM。
- **桥（32 位，python32\python.exe mx_bridge.py）**：独占 MX Component，跑 Modbus TCP 服务。

两者用三种方式通信：

| 方向 | 通道 | 内容 |
|---|---|---|
| 桥 → GUI | 子进程 stdout | `__MXSTATE__UP` / `__MXSTATE__DOWN`（MX 是否真的连上） |
| 桥 → GUI | 子进程 stdout | 普通日志行（GUI 原样打到日志框） |
| GUI → 桥 | 同目录 `link.req` 文件 | 写一次 = 请求重新连接 GX 仿真 |

GUI 还通过 TCP 连 `127.0.0.1:<port>` 读 M/Y 等做监视窗口；读失败只影响显示，不代表桥坏了。

> **关键纪律：`app\mx_bridge.py` 和 `release\Catact\mx_bridge.py` 必须完全一致。**
> 只改 `app\` 里的，`build_release.py` 会自动复制过去；**不要直接改 release 里的副本**，否则下次打包被覆盖。

---

## 四、桥的内部逻辑（v1.0.4）

```
main()
 ├─ 解析 --station / --port / --parent-pid
 ├─ Mx()                    建 COM 实例 → Open → verify 回读 D0
 ├─ 起 Worker 线程           CoInitializeEx(STA)，所有 COM 调用都排进这个线程
 ├─ 起 Modbus TCP 服务       0x / 1x / 4x 三张表，FC01/02/03/04/05/06/15/16
 ├─ 起 link_watchdog 线程    每 1 秒看一次仿真进程 + 链路健康
 └─ 主循环                   accept 连接；--parent-pid 看门狗，父进程没了就自杀
```

### 4.1 Mx 会话：连上不等于能用

`ActUtlType.Open()` 返回 0 只代表「COM 对象打开了」，仿真器重启后旧对象可能 **Open 成功但读回来全是 0 / 读失败**。v1.0.4 的规则：

1. `reconnect()` **丢弃旧实例，新建一个 `ActUtlType`**（不是对旧对象 Close→Open）。
2. `Open()` 最多 3 次。
3. `verify()` 读一次 D0；读成功才算连上。
4. 只有 `reconnect()` 成功才向 GUI 发 `__MXSTATE__UP`。

旧实例只丢引用 + `gc.collect()`，不调用可能卡死的 `Close()`。

### 4.2 link_watchdog：谁在决定重连

每轮（1 秒）：

1. 用 `tasklist` 找 `FSimRun3.exe`，同时取 **PID + 进程创建时间** 作为签名。
2. 签名变化（无→有 / 有→无 / 换了新进程）→ 打日志、作废旧会话、安排重连。
3. 已连上时连续 3 次 `probe()` 失败 → 判掉线，立即重连。
4. 收到 `link.req` → 先发一次当前状态（让 GUI 的「正在连接…」落地），`next_try=0` 立刻重连。
5. 失败退避：仿真没启动 10 秒；刚试 1–2 次 0.8 秒；3–5 次 2 秒；更多 4 秒。

> 用 PID + 创建时间而不是只看进程名，是为了识别「关掉仿真又立刻开」——新进程 PID 不同，必须重建会话。

### 4.3 地址规则（不可动，改之前先看交接报告）

- `0x` 线圈：1 = M0；8001 = S0；9001 = B0；**10001 = X0**；11001 = Y0；…
- `1x` 离散：1 = X0；1001 = Y0；…（只读）
- `4x` 寄存器：1 = D0；8001 = W0；10001 = T当前；…
- X/Y 八进制，W/B/SB/SW 十六进制。
- **0x 与 1x 编号重叠但含义不同**：0x 1 是 M0，1x 1 是 X0。开关必须绑 0x，否则写进 M0、读回 X0，画面按下去就回弹。

---

## 五、版本演进（1.0.0 → 1.0.6）

| 版本 | 解决的核心问题 | 关键改动 |
|---|---|---|
| **1.0.0** | 能跑通的最小版本 | 双进程架构、0x/1x/4x 地址表、M 监视窗口 |
| **1.0.1** | 写 D 寄存器崩溃 / 写错地址 | FC16 多寄存器写入偏移一个字节导致 `struct.error`；`SetDevice` 返回码被忽略；0x/1x 编号重叠导致开关静默写到 M0/B8；补每次写入日志（`[写入]`/`[写入未生效]`/`[写拒绝]`/`[地址提示]`） |
| **1.0.2** | 上次桥没退干净，502 被占，启动键变灰 | 桥加 `--parent-pid` 看门狗（GUI 一退出桥 1 秒内自杀）；启动前自动清理残留桥；「停止桥」也能清理 |
| **1.0.3** | 想解决「GX 仿真重启后桥不重连」 | 引入 `link.req` 信号文件、`link_watchdog` 线程、`__MXSTATE__UP/DOWN` 状态上报；GUI 加仿真进程检测、⟳ 刷新按钮、状态灯 |
| **1.0.4** | **1.0.3 引入的回归**：按钮状态机卡死、假绿、仿真重启不重连 | 见第六节 |
| **1.0.5** | 界面偏「网页风」，不符合工控习惯；MX 设置工具路径不固定，找不到时不好打开 | Win7 经典风格重构（见第七节）；新增 MX Environment 分组，自动定位 / 手动定位 / 一键打开 `ActComm.exe` |
| **1.0.6** | 界面只有英文，中文用户不顺手 | 默认中文，`选项 → 语言 → 中文 / English` 可切回原英文；中文用 Microsoft YaHei UI 9（带回退），英文保持 Segoe UI 9；切换后自动重启（见 7.8） |

### 1.0.3 留下的三个坑（本轮根因）

1. **按钮状态机自锁**
   旧 `_refresh_buttons()` 把按钮「当前 state」当判断条件：
   ```python
   if self.btn_start["state"] != "normal":   # ← 自己把自己锁死
       self.btn_start.config(state="disabled")
   ```
   停止桥后调用刷新，启动键已经是 disabled，于是永远 disabled；只有菜单「工具→启动桥」绕过按钮才能再启动。禁用时只改 `bg` 不改 `fg/cursor`，视觉上仍是粉色可点。

2. **假绿**
   1.0.3 只要 `mx_up=True` 就把灯判绿，没有回读校验。仿真重启后旧 COM 对象「Open 返回 0、读回来全 0」，GUI 仍显示已连接。

3. **对旧 COM 对象 Close→Open**
   `Mx.reopen()` 在同一个对象上 `Close()` 再 `Open()`。仿真器已经换了进程，旧会话的管道失效，`Open` 可能仍返回 0，但读不到数据；表现为「桥一直开着，仿真关了再开，必须断桥重开」。

另外还有一个隐藏雷：中文 Windows 的 `tasklist` 输出是 GBK，1.0.3 用 `subprocess.run(..., text=True)` 在 UTF-8 解释器里会抛 `UnicodeDecodeError`；异常被 `_probe_loop` 吞掉后，仿真检测永久失效。

---

## 六、v1.0.4 本轮改了什么（2026-11-18）

### 6.1 用户报的问题（原始清单）

1. 工具栏「▶ 启动桥 / ■ 停止桥」逻辑错：点启动后启动键灰掉是预期，但**停止后启动键仍然是灰的，点不动**，只能走「工具 → 启动桥」菜单。
2. 没启动时「停止桥」仍显示粉色可点（视觉误导）；三个键的禁用样式不一致。
3. 「⟳ 刷新」逻辑不清：它应该只是**手动重连的备用方案**，不能把桥停掉，也不能连点。
4. 桥一直开着时，把 GX 仿真关掉再开，Catact 显示「桥已连接」，但 EBPro 数据不动；必须「断开桥 → 再启动桥」才恢复。
5. 希望桥**实时检测 GX 仿真是否启动**，检测到就自动连；刷新只作兜底。
6. 交付免安装版；改前备份；每一步写日志。

### 6.2 改动清单

**`app\main.py`**

- 顶部加 `APP_VERSION = "1.0.4"`，窗口标题带版本；「关于」显示版本与本次改动。
- 新增纯函数 `button_states(running, starting=False)`，把「什么时候哪个键能点」变成可单测的规则：
  - 运行中 → 启动 disabled / 停止 normal / 刷新 normal
  - 启动中 → 三个全 disabled（防双击）
  - 未启动 → 启动 normal / 停止 disabled / 刷新 disabled
- `_refresh_buttons()` **只读 `self.bridge.running` 和 `_starting`**，不再读按钮自身 state。
- 新增 `_set_btn()`：统一设置 `state / bg / fg / disabledforeground / cursor`；禁用底色 `#dcdcdc`、字 `#8a8a8a`、光标 `arrow`，一眼能看出不可点。
- `start_bridge()`：`_starting` 防双击；成功 / 失败 / 异常都在 `finally` 刷新按钮；启动时重置 `mx_up`、链路等待计时、刷新忙状态。
- `stop_bridge()`：停止后恢复启动键、禁用停止/刷新，重置链路等待状态。
- `refresh_link()`：仅桥运行时可用；2 秒忙状态防连点；写 `link.req`；状态灯转黄显示「正在重新连接 GX 仿真…」；4 秒后若仍无状态回报，提示「桥可能卡住，可停止后重启」。
- `_probe_loop()`：仿真进程 1.2 秒查一次（原来 0.4–1.0 秒起一次 `tasklist`，太重）；`check_gx()` 改为直接读 bytes 判断 `b"FSIMRUN3"`，绕开 GBK 解码坑。
- `_tick()`：状态灯**只有 `mx_up is True` 才绿**；`False/None` 都黄；工具栏实时显示「仿真 ● 运行中 / ○ 未运行」。
- 兜底：桥 + 仿真都在跑、5 秒还没连上且没补发过 → 自动补写一次 `link.req`。
- `BridgeProc.stop()` 关闭 stdout 句柄，消除 `ResourceWarning`。

**`app\mx_bridge.py`**

- 新增 `rc_text()`，返回码统一打十六进制（如 `0xF1000020`）。
- `Mx.__init__` = `_make()` + `_open(tries=2)` + `verify()`。
- 新增 `_make()`：每次重连**新建** `ActUtlType` 实例，重设逻辑站号、重取 `pdisp/vtbl/invoke`。
- 新增 `_drop_session()`：只丢引用 + `gc.collect()`，不调用可能卡死的 `Close()`。
- `reconnect()`：丢旧实例 → 新实例 → `Open` 3 次 → `verify` 2 次；`reopen = reconnect` 兼容旧名。
- `verify()`：读 D0 校验，读不到就判失败。
- `invalidate()`：仿真停止时作废旧会话。
- `Worker.run()` 增加 `CoInitializeEx(None, 0x2)` / `CoUninitialize()`——否则工作线程里 `CreateObject` 报「尚未调用 CoInitialize (-2147221008)」。
- 新增进程签名：`SIM_PROC="FSimRun3.exe"`、`proc_create_time(pid)`（`OpenProcess(0x1000)` + `GetProcessTimes`）、`sim_proc_info()`（`tasklist` 读 bytes 后宽容解码，返回 `(pid, ctime)` 或 `None`）。
- 重写 `link_watchdog()`：按仿真签名变化触发；掉线 3 次 probe 判死；刷新请求无条件先回报状态；失败按阶梯退避；只有 `reconnect` 成功才发 UP。
- 所有 COM 调用继续走 Worker 线程，GUI 的启动/停止不阻塞。

### 6.3 本轮验证

| 测试 | 内容 | 结果 |
|---|---|---|
| `py -3 tests\test_offline.py` | 35 项：协议、地址、FC16、按钮状态机（含「停止后启动恢复 normal」）、重连必须新建实例、Open 成功但回读失败必须判 DOWN、`rc_text`、`sim_proc_info` | 35/35 OK |
| `py -3 tests\test_gui_state.py` | 5 项：真实 tkinter 建 App 后 withdraw，验证 idle / running / 停止恢复 / 禁用灰样式 / 刷新忙 | 5/5 OK |
| `py -3 tests\test_gui_bridge_flow.py` | 1 项端到端（1502 端口真拉桥）：启动→按钮互斥→日志出现「Modbus TCP 已启动 127.0.0.1:1502」「未连接 GX 仿真」→刷新写信号且不停桥→停止后按钮恢复 | OK（约 9 秒） |
| 桥裸跑（仿真未启动） | `python32.exe mx_bridge.py --port 1502`：`Open rc=0xF1000020`、`__MXSTATE__DOWN`、等待仿真、刷新后重连仍 DOWN，无假 UP | 通过 |
| 进程签名 | 把 `python32\python.exe` 复制成 `%TEMP%\fsim_fake\FSimRun3.exe` 跑 sleep：`sim_proc_info()` 返回 `(pid, ctime)`；杀掉后返回 `None` | 通过 |
| 仿真启停转变 | 桥运行中启动 / 停止 fake `FSimRun3.exe`，日志出现「检测到 GX Simulator3 已启动」「已停止，桥继续监听 502」 | 通过 |

> 测试纪律：**禁止用 `Stop-Process -Name FSimRun3` 这种按名字杀进程的方式做测试**，会误杀用户真实的 GX 仿真器。只能杀自己 `Start-Process` 拿到 PID 的那个进程。
> （本轮测试中曾误杀一次真实仿真进程 PID 5368，用户重新点「模拟开始」即可恢复，不影响工程文件。）

### 6.4 已知限制

- `verify()` 只读 D0。若仿真器 D0 读取被特殊配置挡住，可能误判未连上；正常 FX5U 工程不会。
- 刷新是「请求重连」，不是「强制重建 TCP 监听」；桥进程本身卡死时，刷新无效，需要停止/启动桥。
- EBPro 的 Modbus 超时通常 1–3 秒；仿真重启的空窗期内，HMI 可能弹一次「Device No Response」，属正常。

---

## 七、UI 改版与语言设置（1.0.5 / 1.0.6）

### 7.1 需求与边界

用户提供 `ui.txt` 作为界面规范：**Win7 经典工控 HMI 风格**——系统灰、Segoe UI 9pt、3D 凸起/凹陷、直角无圆角、无渐变、无阴影、无动画、英文菜单、左侧工程树 + 右侧分组框画布 + 底部多格状态栏。

`ui.txt` 的业务内容写的是信捷 DS5L 200W 伺服（参数 / IO / 报警 / 趋势），与 Catact 现有业务（桥控制、仿真状态、M/X/Y/D 监视、写入日志）不匹配。经用户确认，采取：

- **只套视觉风格**，不新增伺服参数 / IO / 报警 / 趋势页面；
- 保留 Catact 全部原有功能；
- 直接改代码并打包。

### 7.2 视觉规范落地

| 规范 | 实现 |
|---|---|
| 系统灰底 | `BG / BAR / PANEL = #f0f0f0`，`BORDER = #808080` |
| 标题栏色 | 非激活 `TITLE_BG = #d4d0c8`，激活 `TITLE_ACTIVE = #0a246a` |
| 状态色 | 绿 `#008000`、红 `#c00000`、黄 `#c8a000`、选中深蓝 `#000080` |
| 字体 | 统一 `Segoe UI`：正文 9、加粗 9、标题 10；移除 Microsoft YaHei / Consolas |
| 控件 | `tk.Button` 原生凸起 `raised bd=2`；按下/选中 `sunken`；输入框白底 `sunken bd=1` |
| 表格 | `ttk.Style` 强制 `theme_use("classic")`；Treeview 灰底、深蓝选中白字、表头灰色凸起 |
| 圆角/渐变/阴影/动画 | 全部不使用；无 hover 动画、无淡入淡出 |
| 菜单 | 全英文：File / Edit / View / Options / Help |
| 工具栏 | `▤ New`（清日志）、`▣ Open`（地址换算）、`▥ Save`（导出）、`▶ Run`（绿）、`■ Stop`（红）、`↺ Reset`（灰） |
| 主体 | 左 `ttk.Treeview` 工程树；右 `LabelFrame relief="groove" bd=1` 分组框 |
| 状态栏 | 左侧弹性提示 + 5 个凹陷格：Bridge / Addr / Mode / Alarms / Time |
| 监视窗 | 格子 `relief="sunken" bd=1`；1=绿底白字、0=白底黑字、错误=红底白字 |

### 7.3 布局与交互

- 左树结构：`Catact Project` → `Bridge`（Control / Simulation / Settings）、`Devices`（18 个元件）、`Diagnostics`（Write Log / Address Map）、`Help`（Usage / About）。
- 双击 `Devices` 下元件打开/关闭对应监视窗；双击 `Bridge → Control/Simulation` 弹出状态说明，`Settings` 打开桥参数。
- `Diagnostics → Write Log` 聚焦日志区；`Address Map` 聚焦地址表。
- 右侧从上到下：`MX Environment`（v1.0.5 追加）→ `Device Monitor` → `Y Output` → `Monitor Windows` → `Address Reference` → `Write Log`。
- 工具栏/状态栏宽度实测：窗口 1600×1025（125% DPI），工具栏请求宽 773、设备条 877、状态栏 889，均未溢出。

### 7.4 MX Environment：自动定位 + 一键打开

用户现场路径不固定（本机在 `D:\Program Files (x86)\MELSOFT\ACT\Utl\ActComm.exe`），因此新增分组框：

- **状态**：LED + `MX Component: 已安装/未检测到` + 当前 `ActComm.exe` 完整路径。
- **按钮**：`Open MX Utility`（一键打开）、`Locate...`（手动定位）、`Recheck`（强制重新扫描）。
- **自动定位顺序**（`find_mx_utility`）：
  1. `config.json` 里记住的 `mx_utility`；
  2. `%ProgramFiles(x86)%` / `%ProgramFiles%` 下的 `MELSOFT\ACT\Utl\ActComm.exe`；
  3. C–G 盘的 `Program Files (x86)\MELSOFT\ACT\Utl\ActComm.exe` 与 `Program Files\...`；
  4. 注册表 Uninstall（HKLM 64/32 位 + HKCU）里 DisplayName 含 `MX Component` / `MELSOFT` / `GX Works` 的 `InstallLocation`，再拼 `ACT\Utl\ActComm.exe`、`Utl\ActComm.exe`、`ActComm.exe`；
  5. `MELSOFT` 目录下最多 4 层 `os.walk` 兜底找 `ActComm.exe`。
- **缓存**：找到后写入 `config.json` 的 `mx_utility`，下次启动直接用；`Recheck` 用 `force=True` 重新扫。
- **手动定位**：`Locate...` 打开文件选择器；若选的不是 `ActComm.exe` 会二次确认；确认后记住路径并刷新状态。
- **一键打开**：`open_mx_utility()` 直接 `subprocess.Popen([路径], cwd=所在目录)`；找不到时弹确认框引导手动定位。
- 启动 180 ms 后自动执行一次检测；`Options → MX Environment Check` 也会强制刷新并显示完整路径。

本机实测：`mx_utility_path()` 0.02 s 返回 D 盘路径，`mx_installed() = True`。

### 7.5 本轮验证

| 测试 | 内容 | 结果 |
|---|---|---|
| `py -3 tests\test_offline.py` | 35 项离线：协议、地址、FC16、按钮状态机、重连规则 | 35/35 OK |
| `py -3 tests\test_gui_state.py` | 5 项：idle / running / 停止恢复 / 禁用灰样式 / 刷新忙 | 5/5 OK |
| `py -3 tests\test_gui_layout.py` | 10 项：classic 主题、英文菜单、工具栏/设备条/状态栏/MX 分组不溢出、树根、监视格 sunken | 10/10 OK |
| `py -3 tests\test_gui_bridge_flow.py` | 1 项端到端（1502 端口真拉桥）：启动→按钮互斥→刷新→停止 | OK（约 9 秒） |
| MX 自动定位 | `mx_utility_path()` 计时 / `mx_installed()` | 0.02 s / True |

### 7.6 已知偏差（不是 bug）

- **窗口标题栏仍是 Windows 10/11 原生样式**。Win7 的渐变标题栏需要自绘非客户区（`WM_NCPAINT`），代价高且在高 DPI 下易错；本次只统一客户区控件风格。若以后必须完全复刻 Win7，需要单独做 custom chrome。
- 未新增伺服参数 / IO / 报警 / 趋势页——用户明确选择「只套视觉」。
- 没有取得 Catact 主界面的真实截图（桌面控制授权被关闭）；验收依据是 tkinter 真实建窗的尺寸 / 主题 / 控件属性测试 + 用户实机观感。

### 7.7 本轮改动文件

- `MXBridgeTool\app\main.py`：视觉重构 + 左树 + `MX Environment` 分组 + 自动定位/手动定位/一键打开。
- `MXBridgeTool\tests\test_gui_layout.py`：新增布局 / 主题 / 树 / 监视格 / MX 分组测试。
- `MXBridgeTool\build_release.py`、`Catact.iss`、`README.txt`：版本号与说明同步 1.0.5。

### 7.8 v1.0.6 语言设置（2026-11-18）

**需求**：设置里能选语言，默认中文，可切回 1.0.5 原来的英文；中文字体要合适。

**实现**（只改 `app\main.py`，桥逻辑未动）：

- 全局 `LANG` 默认 `"zh"`，`DEFAULT_CFG["lang"] = "zh"`；`config.json` 没有 `lang` 时也按中文。
- 新增 `_TR` 双语表 + `T(key, **kw)`：静态文案与动态状态（未启动 / 检测中 / 已连接 / 等待仿真 / 连接中 / 启动中 / 端口占用）都走 `T()`，避免切换后残留英文。
- `_apply_fonts()`：中文按 `Microsoft YaHei UI → Microsoft YaHei → SimSun → Segoe UI` 取第一个已装字体，9pt；英文固定 `Segoe UI 9`，与 1.0.5 一致。
- 菜单 `Options → Language` 两个 radiobutton：`中文` / `English`；选择后 `change_language()` 弹确认，写 `cfg["lang"]` 并 `save_cfg()`，再 `restart_app()`。
- `save_cfg()` 改为返回成功/失败；目录不可写时弹出提示并回退语言，不会出现「选了英文、重启还是中文」。
- `restart_app()`：先停桥；打包版 `Popen([sys.executable], cwd=APP_DIR)`，源码版 `Popen([sys.executable, __file__], cwd=APP_DIR)`，随后 `destroy()`。
- 翻译覆盖：菜单、工具栏、工程树、全部分组框、状态栏、MX 分组、监视窗口标题/列表、桥与仿真状态弹窗、Bridge Settings、导出、Usage/About、MX 检查。
- 保持原样：运行日志正文、M/X/Y/D 元件名、0x/4x 地址、CSV 表头、地址换算窗口原有中文标签。

**验证**：

| 测试 | 内容 | 结果 |
|---|---|---|
| `test_gui_layout.py` | 14 项：默认中文菜单、`T()` 中英切换、中文字体、布局不溢出、语言保存并重启（mock）、config 不可写时回退 | 14/14 OK |
| `test_gui_state.py` | 5 项按钮互斥 / 灰色禁用 | 5/5 OK |
| `test_offline.py` | 35 项桥逻辑 | 35/35 OK |
| `test_gui_bridge_flow.py` | 1502 端口端到端启动→停止 | 1/1 OK |
| 文案实测 | 中文标题 `Catact 1.0.6 - FX5U Modbus 桥`、字体 `Microsoft YaHei UI 9`；英文 `File / ▶ Run / Open MX Utility`、`Segoe UI 9` | 通过 |

**已知限制**：语言切换是「写配置 + 重启进程」，会停桥；重启后需再点一次「▶ 启动」。没有做不重启的热切换，因为 Tk 菜单/树/分组框的文本全部要重建，热切换容易漏改，重启最稳。中文界面像素观感仍未截图确认（桌面控制授权被关闭），验收依据是真实 Tk 建窗的字体/尺寸/控件属性测试。

**交付**：`2_Catact_1.0.6_免安装版.zip`（1345 个文件，28.8 MB，已排除 `config.json` / `modbus_debug.log`）、解压目录 `2_Catact_1.0.6_免安装版\Catact\`、`3_Catact_1.0.6_安装包.exe`。成品 exe 实测：默认中文标题 `Catact 1.0.6 - FX5U Modbus 桥`；`config.json` 写 `"lang":"en"` 后标题 `Catact 1.0.6 - FX5U Modbus Bridge`。

---

## 八、以后怎么改（标准流程）

### 8.1 改代码前

1. 先在项目根目录建备份：
   `备份_修改前_v<版本>_<YYYYMMDD_HHMM>\`
   至少包含：`app\main.py`、`app\mx_bridge.py`、当前免安装 zip、当前 Catact.exe、当前 release 的 `mx_bridge.py`，并写 `_备份说明.txt`。
2. 读 `1_Catact交接报告.md` 的「地址表 / 坑」两节，确认没碰不能动的东西。
3. 只改 `MXBridgeTool\app\` 下的源码；**不要**改 `release\Catact\` 里的副本。

### 8.2 改完必须跑

```powershell
cd 'D:\Project folder\删掉\91\软件制作文件夹\MXBridgeTool'
py -3 tests\test_offline.py          # 必须 35+ 全过
py -3 tests\test_gui_state.py        # 按钮状态（5 项）
py -3 tests\test_gui_layout.py       # 经典风格 / 布局 / MX 分组（10 项）
py -3 tests\test_gui_bridge_flow.py  # 端到端，确认 1502 端口空闲
```

现场再补两项（有 GX 仿真时）：

- 仿真停止 → 启动桥：日志应显示 `Open rc=0xF1000020`、`__MXSTATE__DOWN`，灯黄；启动仿真后 2–3 秒内自动变绿。
- 桥保持运行 → 关仿真 → 再开仿真：日志应出现「检测到 GX Simulator3 已启动」，并自动重连变绿；EBPro 数据恢复。

### 8.3 重打包顺序（与交接文档一致）

```powershell
cd 'D:\Project folder\删掉\91\软件制作文件夹\MXBridgeTool'
py -3 build_release.py
```

脚本会：

1. 跑 `test_offline.py`（不过就中止）；
2. `PyInstaller --onefile --windowed --name Catact --icon app\catact.ico app\main.py`；
3. 复制 `dist\Catact.exe`、`app\mx_bridge.py`、`app\catact.ico`、`README.txt` 到 `release\Catact\`；
4. 调 `ISCC.exe Catact.iss` 出安装包；
5. 打 `release\Catact_<VER>_便携版.zip`，复制到根目录 `2_Catact_<VER>_免安装版.zip`。

打包后自检：

- 解压 zip 到新目录，双击 `Catact.exe`，标题应显示 `v1.0.5`；
- 不启动仿真点工具栏「▶ Run」→ Run 变灰、Stop/Reset 可点、灯黄；
- 点「■ Stop」→ Run 恢复、Stop/Reset 变灰；
- 启动 GX 仿真 → 灯自动变绿（最多等 3 秒）；
- 右侧 `MX Environment` 应显示 `ActComm.exe` 路径，点 `Open MX Utility` 能打开站号设置工具。

### 8.4 版本号同步清单（容易漏）

- `app\main.py` 的 `APP_VERSION`
- `build_release.py` 的 `VER`
- `Catact.iss` 的 `AppVersion` / `AppVerName` / `OutputBaseFilename`
- `README.txt` 首行
- 项目根 `4_用户使用说明.txt`、`0_先看这里.txt`、`10_Catact_<版本>_...说明.txt` 里提到的版本

---

## 九、调试速查

| 现象 | 先看哪里 | 大概率原因 |
|---|---|---|
| 启动键灰、点不动 | 菜单「工具→启动桥」是否能点 | 旧版按钮自锁；1.0.4 已修。若仍灰，看是否 `_starting` 卡住（启动中异常） |
| 灯绿但 EBPro 数据不动 | 桥日志最后 10 行 | 假绿（旧版）；1.0.4 只有回读 D0 成功才绿。检查是否连到了别的进程占的 502 |
| 灯黄，日志 `Open rc=0xF1000020` | GX Works3 是否「模拟开始」 | 仿真没 RUN / 逻辑站号不是 1 / MX Component 没装 |
| 灯黄，日志 `read ... rc=0xF0000004` | 同上 | 会话失效：仿真重启过，等自动重连或点刷新 |
| 桥启动就退 | `modbus_debug.log`、`--parent-pid` | 502 被占；GUI 已退出触发看门狗；逻辑站号错 |
| 502 被占 | `Get-NetTCPConnection -LocalPort 502` | 上次残留桥；点「启动桥」会自动清；或按 PID 杀 |
| 开关按下去回弹 | 日志有无 `[地址提示]` | 开关绑到了 1x；改 0x（X0=0x 10001，Y10=0x 11009） |
| 写 D 值不对 / 崩溃 | 是否 FC16 多寄存器 | 1.0.1 已修；确认没回退 |
| 桥日志出现 UnicodeDecodeError | `check_gx` / `sim_proc_info` 是否用 text=True | 中文 Windows `tasklist` 是 GBK；必须读 bytes |
| 仿真重启后不自动连 | 日志有无「检测到 GX Simulator3 已启动」 | 仿真进程名不是 `FSimRun3.exe`（版本差异）；或检测线程被异常打死 |
| 找不到 MX 设置工具 | 右侧 MX Environment 路径 | 点 `Locate...` 选 `ActComm.exe`；路径会记进 `config.json` 的 `mx_utility` |

### 常用命令

```powershell
# 端口占用
Get-NetTCPConnection -LocalPort 502 -ErrorAction SilentlyContinue | Select State,OwningProcess

# 找桥进程（按命令行，不要按名字杀）
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*mx_bridge.py*' } |
  Select ProcessId,ParentProcessId,CommandLine

# 只读诊断 MX（必须 32 位）
& '...\MXBridgeTool\app\python32\python.exe' '...\MXBridgeTool\tests\diag_mx.py'

# 看桥写入日志
Get-Content '...\release\Catact\modbus_debug.log' -Tail 30
```

### MX 返回码

| 码 | 含义 |
|---|---|
| `0xF1000020` | 打开失败：仿真没启动 / 站号不对 / MX 环境没配 |
| `0xF0000004` | 读失败：会话失效（仿真重启过）或地址不支持 |
| `0x00000000` | 成功 |

---

## 十、变更记录

| 日期 | 版本 | 内容 | 操作人 |
|---|---|---|---|
| 2026-11-18 | 1.0.6 | 新增语言设置：默认中文，Options → Language 可切回英文；中文 Microsoft YaHei UI 9 / 英文 Segoe UI 9；切换写 config 并重启；布局/双语测试 14 项 | 本轮 |
| 2026-11-18 | 1.0.5 | Win7 经典工控风 UI 重构（系统灰 / Segoe UI / 3D 斜面 / 左树右分组 / 英文菜单 / 多格状态栏）；新增 MX Environment 自动定位 + 手动定位 + 一键打开 ActComm.exe；布局回归测试 10 项 | 本轮 |
| 2026-11-18 | 1.0.4 | 按钮状态机重写；桥改「新建实例 + 回读校验」重连；仿真进程签名实时检测；刷新改手动兜底；编码坑修复；打包免安装版 | 本轮 |
| （上一手） | 1.0.3 | link.req、link_watchdog、__MXSTATE__、GUI 刷新键 | 上一手 |
| （上一手） | 1.0.2 | 父进程看门狗、残留桥清理 | 上一手 |
| （上一手） | 1.0.1 | FC16 偏移、SetDevice 返回码、0x/1x 重叠、写入日志 | 上一手 |
| （上一手） | 1.0.0 | 首版双进程桥 | 上一手 |

---

*本文与 `8_Catact_1.0.4_修复说明.txt`、`10_Catact_1.0.5_UI改版说明.txt`、`11_Catact_1.0.6_语言设置说明.txt` 配套：本文偏维护/交接，说明文件偏「这次改了什么、怎么验」。*
