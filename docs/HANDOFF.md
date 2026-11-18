# Catact 项目交接报告

| 项目 | 内容 |
|---|---|
| 软件名称 | Catact（原名 MX 桥工具 / MXBridgeTool） |
| 版本 | 1.0.0 |
| 交接日期 | 2026-11-18 |
| 当前状态 | 主链路已可用；**HMI 按钮写入（Toggle Switch）仍有未解决问题**，见第 6 章 |
| 代码位置 | `D:\Project folder\删掉\91\软件制作文件夹\MXBridgeTool\` |
| 交付形态 | 便携版（免安装 zip）已交付；Inno Setup 安装包同步保留 |

---

## 1. 这个软件是干什么的

### 1.1 一句话

**把 GX Works3 的 FX5U 仿真器（GX Simulator3）包装成一台 Modbus TCP 从站，让威纶通 EBPro 在没有真实 PLC 的情况下也能连上、调试 HMI 画面。**

### 1.2 业务问题

调 HMI 画面（EBPro 工程）的传统流程是：画面上绑好 PLC 地址 → 连真机 → 下载 → 在机台旁一个个点按钮验证。问题在于：

- 项目早期没有样机 / PLC 不在手边，画面根本没法调；
- 逻辑（梯形图）改一版就要重新跑现场；
- 用 EBPro 的"离线模拟"又验证不到真实的地址映射和通信时序。

GX Works3 自带仿真器能跑梯形图，逻辑是"活"的；但它是三菱私有协议，EBPro 只会 Modbus TCP。**中间缺一层协议转换，这就是本项目。**

### 1.3 使用流程（4 步）

```
1. GX Works3 打开 FX5U 工程 → 调试 → 模拟开始（确认仿真器 RUN）
2. 打开 Catact → 点「启动桥」→ 状态灯变绿
3. EBPro：设备类型 MODBUS TCP/IP，IP 127.0.0.1，端口 502，站号 1
4. 元件地址用软件里的「地址换算」窗口查（输 M0 出 0x 1）
```

之后：EBPro 里点按钮 → Modbus 写 → 桥 → MX → 仿真器里的软元件变化 → 梯形图动作 → 输出 Y 变化 → 桥读回 → EBPro 指示灯亮。**闭环。**

### 1.4 衍生能力（GUI 工具）

软件本身还是一个 PLC 调试工具，不只是个后台桥：

- 点元件按钮（M/X/Y/D/W/T/C/L/S/B/SM/F/ST/SB/SD/Z/R/SW）弹出现实时的监视窗口，1=绿底、0=灰字，可右键强制置 1/置 0；
- 元件名 ⇄ Modbus 地址双向换算（自动处理八进制/十六进制）；
- 顶部 Y 输出行实时显示 Y0–Y17 状态；
- 桥的启停、日志、MX 环境自检都集成在界面里。

---

## 2. 系统架构

### 2.1 链路

```
┌──────────────┐   私有协议     ┌───────────────┐   Modbus TCP    ┌──────────┐
│  EBPro 工程   │ ────────────▶ │   Catact 桥    │ ◀────────────── │  调试用   │
│ (HMI 画面)    │  127.0.0.1:502│  (32 位进程)   │                 │  GUI 窗口 │
└──────────────┘                └───────┬───────┘                 └──────────┘
                                        │ MX Component (COM)
                                        │ ActUtlType，逻辑站号 1
                                ┌───────▼────────┐
                                │ GX Simulator3  │
                                │ (FX5U 仿真器)   │
                                └───────┬────────┘
                                        │ 运行
                                ┌───────▼────────┐
                                │  GX Works3     │
                                │  (梯形图工程)   │
                                └────────────────┘
```

### 2.2 两个进程，为什么必须分开

| 进程 | 位数 | 职责 | 原因 |
|---|---|---|---|
| `Catact.exe`（GUI） | 64 位 | 界面、监视、轮询、拉起桥 | 打包简单、Tk 稳定 |
| 桥（`python32\python.exe mx_bridge.py`） | **32 位** | Modbus 服务端 + MX 访问 | **MX Component 的 `ActUtlType` 是 32 位 COM 组件，64 位进程加载不了** |

GUI 通过 `subprocess.Popen` 拉起桥，把桥的 stdout 用管道收回来打到日志框里（`BridgeProc` 类）。桥是一个独立可执行单元，**也可以完全脱离 GUI 单独命令行运行**：

```bat
python32\python.exe mx_bridge.py --station 1 --port 502
```

---

## 3. 运行环境

| 组件 | 要求 | 说明 |
|---|---|---|
| Windows | 10 / 11 x64 | 开发机 2560×1440、125% 缩放（DPI 120） |
| **MX Component** | 三菱官方，必装 | 提供 `ActUtlType.ActUtlType`；商业组件，无法打包分发 |
| GX Works3 + GX Simulator3 | FX5U 工程 | 逻辑站号必须在 Communication Settings Utility 里建好 |
| EBPro | 威纶通 | 设备类型 MODBUS TCP/IP |
| 32 位 Python | 3.12.4 embeddable | 已内置在 `app\python32\`，含 pywin32 + comtypes |
| 64 位 Python | 3.10+ | **仅开发用**，打包后不需要 |
| PyInstaller | 6.21 | 打 `Catact.exe` |
| Inno Setup | 6.x | 打安装包 |

**逻辑站号配置**（MX 侧，一台机器只需配一次）：

```
PC I/F     = GX Simulator3
CPU type   = FX5U
Port No.   = 0
System No. = 1
PLC No.    = 1
```

---

## 4. 目录结构与文件职责

```
MXBridgeTool\
├─ app\
│  ├─ main.py            1281 行  GUI 全部代码（tkinter）
│  ├─ mx_bridge.py        668 行  桥：MX Component → Modbus TCP
│  ├─ python32\                  32 位便携 Python（桥的运行环境，勿删）
│  ├─ catact.ico                 多尺寸图标（16/20/24/32/48/64/128/256）
│  └─ config.json                自动生成：host / port / station / refresh_ms / python32
├─ dist\Catact.exe               PyInstaller 单文件产物
├─ release\Catact\               便携版目录（exe + 桥脚本 + python32 + README）
├─ installer\Catact_Setup_1.0.0.exe   Inno Setup 安装包
├─ Catact.spec                   PyInstaller 配置
├─ Catact.iss                    Inno Setup 脚本（UTF-8 BOM）
├─ ChineseSimplified.isl         安装向导简体中文
├─ 启动.bat                      开发模式启动器（走系统 Python，跑 app\main.py）
├─ README.txt                    面向最终用户的使用说明
├─ 地址对照表.html                地址映射一览（浏览器打开）
└─ 界面预览.png                   界面截图
```

### main.py 内部结构（按出现顺序）

| 类 / 函数 | 职责 |
|---|---|
| `enable_dpi()` / `DPI` / `S` | 声明 Per-Monitor V2 DPI 感知，`S = DPI/96` 作为全局尺寸缩放系数 |
| `light_titlebar()` | DWM attr 20/19 把原生标题栏改成浅色，配 GX Works 灰蓝风格 |
| `move_window_fast()` | Win32 `SetWindowPos`（NOSIZE\|NOZORDER\|NOACTIVATE）移动窗口，绕开 Tcl 层 |
| `AddrMap` | 地址映射表（BIT/WORD）、进制、`name_to_addr`、`addr_to_name`、`mirror_addr` |
| `MbClient` | Modbus TCP 客户端，**持久连接**，断线自动重连 |
| `BridgeProc` | 拉起/停止 32 位桥进程，stdout → 队列 → 日志 |
| `FloatWindow` | 原生 `Toplevel` 基类：transient、浅色标题栏、DPI 缩放、位置追踪、`alive` 标志 |
| `MonitorWindow` | 监视网格：10 列 × 16 行可见，滚动看全量（400 点），增量刷新 |
| `ConvertWindow` | 地址换算窗口（双向，470×158） |
| `App(tk.Tk)` | 主窗口：菜单、工具栏、元件行、输出行、工作区分栏、日志、轮询、桥控制 |

### mx_bridge.py 内部结构

| 类 / 函数 | 职责 |
|---|---|
| `Mx` | MX Component 封装：`Open()` 重试、`ReadDeviceBlock`（走裸 `IDispatch::Invoke`）、`SetDevice`、`reopen()` |
| `Worker` | **独占 COM 的工作线程**（COM 线程亲和性），`call(fn, *args, timeout=5)` 同步取结果 |
| `Plc` | 业务层封装：`read_words` / `read_bits`（16 点解包）/ `write_bits` / `write_words` |
| `BIT_MAP` / `WORD_MAP` | 分区地址表（见第 5.3 节） |
| `resolve` / `devname` / `seg_at` | 地址 → 软元件名（处理八/十六进制） |
| `read_bits_range` / `read_words_range` | 跨段拆分读取 |
| `handle_pdu` | Modbus 功能码分发 |
| `client_worker` | 每个 TCP 连接一个线程；只有真正发过请求才打"连接/断开"日志 |
| `sim_pid` / `watch_sim` | 看门狗：每 3s 查 `FSimRun3.exe` PID，变了就重连 |
| `main` | argparse（--station / --port / --host / --tlb） |

---

## 5. 关键实现细节（踩过的坑都在这）

### 5.1 MX Component 访问

**坑 1：`ReadDeviceBlock` 的签名 comtypes 处理不了。**
`ReadDeviceBlock(sDevice: BSTR, lSize: long, lplData: long*)` 第三个参数是通过引用传数组，comtypes 的普通方法调用拿不到地址。所以 `Mx.__init__` 里手工干了两件事：

1. `GetModule(tlb)` + `CreateObject("ActUtlType.ActUtlType", interface=...)` 拿到接口指针；
2. 从 vtable 第 6 项取 `IDispatch::Invoke` 函数指针，**手工组装 `DISPPARAMS` + `VARIANT`**（`VT_I4|VT_BYREF` 指向缓冲区、`VT_BSTR` 指向设备名），DISPID = 6。

写操作（`SetDevice`）签名简单，直接走 comtypes 方法调用即可。

**坑 2：位元件是 16 点打包的。**
`ReadDeviceBlock("M0", 16)` 返回的是 **16 个 WORD**（不是 16 个位），每个 WORD 装 16 个点，LSB 是段内第 1 点。所以读 M0 一个点会返回一个 WORD，用户曾经看到"Y0 的值是 2"就是这个原因。`Plc.read_bits` 的做法：把起点对齐到 16 的整数倍 → 算需要几个字 → 读回后按 `(k//16, k%16)` 逐位取出。

**坑 3：`Open()` 返回 0xF1000020。**
上一次桥异常退出时 MX 端还留着占用。处理：`Open()` 最多重试 6 次、间隔 1s。

**坑 4：仿真器重启后桥读到全 0。**
GX 仿真器一重启，旧的 COM 会话就失效但 `Open()` 不报错。处理：`watch_sim()` 每 3 秒用 `tasklist /FI "IMAGENAME eq FSimRun3.exe" /FO CSV /NH` 取 PID，**PID 变化即认为仿真器重启**，调 `reopen()`（Close → 重试 Open）。

**坑 5：COM 线程亲和性。**
所有 COM 调用必须发生在创建对象的那个线程。`Worker` 线程独占 `Mx` 对象，其它线程通过队列提交任务并 `Event.wait(timeout=5)` 等结果；超时抛 `TimeoutError("MX 调用超时")`——这也是日志里 `[读失败] ... MX 调用超时` 的来源（多半是仿真器没 RUN）。

### 5.2 Modbus TCP 服务

| 功能码 | 支持 | 说明 |
|---|---|---|
| 01 读线圈 | ✅ | → 0x 区 |
| 02 读离散输入 | ✅ | → 1x 区 |
| 03 / 04 读保持/输入寄存器 | ✅ | 都映射到 4x 分区表 |
| 05 写单线圈 | ✅ | → 0x 区，`SetDevice` |
| 06 写单寄存器 | ✅ | → 4x 区 |
| 0F 写多线圈 | ✅ | 逐点写 |
| 10 写多寄存器 | ✅ | 逐点写 |
| 17 读写组合 / 2B 设备识别 | ❌ | 目前没实现（EBPro 默认不用） |

**坑 6：EBPro 按 32 字对齐整块读，块会跨段。**
比如读 0x 的 8993 起 32 点，实际横跨「S 段尾 → B 段头 → X 镜像段头」三个段。如果不拆分，桥会用错误的设备名去读一整块，返回的数据整体错位（用户当时的现象是 Y0/Y1 读不到 / 值对不上）。
处理：`read_bits_range` / `read_words_range` 逐段推进，每段单独调 MX，最后拼接；落在表外的地址补 0（**返回 0 而不是异常**，否则 EBPro 会弹通信错误）。

**坑 7：GUI 自己的探测连接刷屏。**
状态灯每 300ms 连一下 502 再关闭，桥把它当成 EBPro 会话打印出来，日志里出现"连接/断开"狂刷、端口号递增。
处理：`client_worker` 里加 `served` 标志，**只有真正发过 Modbus 请求的连接才打日志**；同时 GUI 的 `MbClient` 改为持久连接（不再每请求新建 TCP）。

### 5.3 地址映射表 ★核心

设计原则：Modbus 只有 4 个区（0x/1x/3x/4x），三菱软元件有 16 种。**把每个区切成固定段落，一次定死**，以后不管用户用哪种元件都不用改代码。

#### 0x 区（线圈，**可读可写**）

| 显示地址 | 软元件 | 进制 | 备注 |
|---|---|---|---|
| 1 – 8000 | M0 – M7999 | 10 | 内部继电器 |
| 8001 – 9000 | S0 – S999 | 10 | 步进继电器 |
| 9001 – 10000 | B0 – B3E7 | **16** | 链接继电器 |
| 10001 – 11000 | X0 – X1777 | **8** | **X 可写镜像** |
| 11001 – 12000 | Y0 – Y1777 | **8** | **Y 可写镜像** |
| 12001 – 13000 | T0 – T999 | 10 | 触点镜像 |
| 13001 – 14000 | C0 – C999 | 10 | 触点镜像 |
| 14001 – 15000 | L0 – L999 | 10 | 锁存继电器镜像 |
| 15001 – 16000 | SM0 – SM999 | 10 | 特殊继电器镜像 |
| 16001 – 17000 | F0 – F999 | 10 | 报警器镜像 |
| 17001 – 18000 | ST0 – ST999 | 10 | 累计定时器触点镜像 |
| 18001 – 19000 | SB0 – SBFFF | **16** | 链接特殊继电器镜像 |

> **镜像规则：`0x 地址 = 1x 地址 + 10000`**（X0 → 10001，Y10 → 11009，L0 → 14001）

#### 1x 区（离散输入，**只读**）

| 显示地址 | 软元件 | 进制 |
|---|---|---|
| 1 – 1000 | X0 – X1777 | 8 |
| 1001 – 2000 | Y0 – Y1777 | 8 |
| 2001 – 3000 | T 触点 | 10 |
| 3001 – 4000 | C 触点 | 10 |
| 4001 – 5000 | L | 10 |
| 5001 – 6000 | SM | 10 |
| 6001 – 7000 | F | 10 |
| 7001 – 8000 | ST 触点 | 10 |
| 8001 – 9000 | SB | 16 |

#### 4x 区（保持寄存器，可读可写）

| 显示地址 | 软元件 | 进制 | 备注 |
|---|---|---|---|
| 1 – 8000 | D0 – D7999 | 10 | 数据寄存器 |
| 8001 – 9000 | W0 – WFFF | 16 | 链接寄存器 |
| 9001 – 10000 | T 当前值 | 10 | |
| 10001 – 11000 | C 当前值 | 10 | |
| 11001 – 12000 | ST 当前值 | 10 | |
| 12001 – 13000 | SD | 10 | 特殊寄存器 |
| 13001 – 21000 | ZR | 10 | **仿真器不支持，读会报错** |
| 21001 – 21020 | Z | 10 | 变址寄存器 |
| 22001 – 30000 | R | 10 | 文件寄存器 |
| 30001 – 31000 | SW | 16 | 链接特殊寄存器 |

#### 速记规则

- **按钮、数值输入 → 0x / 4x**（可写）；**指示灯、只读状态 → 1x**（只读）
- 进制：X、Y 八进制；W、B、SB、SW 十六进制；其余十进制
- 例：`M10 → 0x 11`、`S0 → 0x 8001`、`B0 → 0x 9001`、`Y1 → 1x 1002`、`D100 → 4x 101`、`W1F → 4x 8032`

#### 为什么要有"可写镜像"（重要设计取舍）

三菱的 X/Y 在语义上是"输入/输出"，很自然地放进了只读的 1x。但 **EBPro 的 Toggle Switch 绑在 1x 上写不进去**（1x 是 FC02 只读区），现象就是「按不下去」或「一按就回弹」。所以 0x 区额外开了一套与 1x 一一对应的镜像段，让用户能给 X/Y 这种"软元件"配可写地址。

**这个设计是有代价的**：一个按钮要配两个地址（0x 写、1x 读），用户极易配错，也是当前遗留问题的根源之一。第 6.1 节给了彻底方案。

### 5.4 GUI 实现要点

| 机制 | 实现方式 | 解决的问题 |
|---|---|---|
| DPI 清晰 | 启动最早期 `SetProcessDpiAwarenessContext(PMv2)`；读真实 DPI 算 `S=DPI/96`；所有尺寸 ×S；Tk `scaling` 让磅值字体正确放大 | 125% 缩放下文字发虚（位图被系统拉伸 1.25 倍） |
| 原生子窗口 | `tk.Toplevel` + `transient(parent)` + `overrideredirect(False)`，DWM 浅色标题栏 | Canvas 自绘窗口拖动有残影、跟不上鼠标 |
| 拖动跟随 | 主窗口 `<Configure>` → **15ms 节流合并**（`_move_pending` 标志）→ `SetWindowPos` 批量子窗口 | 逐像素触发 Tcl 层 + 每窗口 3 次同步调用导致的卡顿 |
| 轮询 | 单个后台线程，每 `refresh_ms`（默认 400）读所有窗口一次；结果塞 `queue`，主线程 `_tick`（300ms）取出并 `apply` | 主线程不阻塞，UI 不假死 |
| 增量刷新 | `MonitorWindow._last` 缓存上一帧，只 `.config()` 变化的格子 | 400 格全量重绘每帧导致的卡顿 |
| 线程安全 | 窗口存活状态用 `alive` 布尔标志（主线程维护），**不再从轮询线程调 `winfo_exists()`** | Tk 跨线程调用崩溃 |
| 持久连接 | `MbClient` 内部保存 socket，异常时重连 | 每请求新建 TCP → 日志刷屏 + 端口耗尽 |

---

## 6. 当前问题（接手请从这里开始）

### 6.1 【P0 · 未解决】EBPro 上 Toggle Switch 按不下去 / 一按就回弹

#### 现象

用户新做的触控屏工程里，三个开关全部失效：

| 元件 | 原绑定地址 | 语义 |
|---|---|---|
| TS_0 | `1x-1` | 想按 X0 |
| TS_2 | `1x-2` | 想按 X1 |
| TS_1 | `1x-1009` | 想按 Y10 |

#### 已定位的部分

`1x` 是 Modbus **离散输入区（FC02），只读**。EBPro 的 Toggle Switch 绑在这里，写入请求要么被桥以异常码 04 拒绝、要么根本没发出去；即便写成功，下一轮轮询读到 PLC 的真实值立刻把画面状态覆盖回去 → 表现就是"按不下去"或"一按回弹"。

同一个坑之前已经踩过一次（S/B 按钮），当时的解法是把 S/B 从 1x 挪到 0x 可写区。

#### 已做的修复（本次）

给 0x 区增加了 1x 全部段的**可写镜像**（规则 `0x = 1x + 10000`），并把换算器/速查表/README/桥的分区表全部同步：

```
x0 按钮 → 0x 10001     （灯仍用 1x 1）
x1 按钮 → 0x 10002     （灯仍用 1x 2）
y10 按钮 → 0x 11009    （灯仍用 1x 1009）
```

离线单元测试（`_mirrortest.py`，stub 掉 MX）已验证：映射换算、跨段拆分、FC05 写入路由到 X 软元件全部正确。

#### 仍然存在的问题

用户反馈"**现在问题还是有**"。目前**无法确定**是以下哪一种：

1. **用户还没在 EBPro 里改地址**（最可能）——软件侧改完了，但 HMI 工程里三个开关的地址还是 `1x-*`；
2. **MX 拒绝写 X/Y**——`SetDevice("X0", 1)` 可能返回错误码。真机上 X 由外部输入驱动，仿真器是否允许写 X/Y 需要实测；
3. **写入成功但读回被覆盖**——比如梯形图里对 X0 有 `RST`/`OUT` 之类逻辑，或者 EBPro 的开关是"瞬时型"而不是"交替型"。

#### 接手后请按这个顺序验证（每条都能定位一层）

**第 1 步：确认 HMI 工程地址已改**

打开 EBPro，看三个 Toggle Switch 的地址栏是不是 `0x 10001` / `0x 10002` / `0x 11009`。如果还是 `1x-*`，先改过来再测——**这一步没做，后面所有验证都没意义**。

**第 2 步：看桥日志有没有"写失败"**

桥的所有写失败都会写进 `app\modbus_debug.log`（32 位进程的工作目录）：

```
[写失败] 0x 10000 read X0 rc=...
[写失败] 0x 10008 ...
```

- 有 `[写失败]` → 说明 MX 拒绝了写 X/Y，走第 3 步；
- 没有 → 说明写成功了，问题在"读回覆盖"，走第 4 步。

> ⚠️ **重要：日志为空 ≠ 写入成功。** 交接前实测过：用户测试时三处
> `modbus_debug.log` 全是 0 字节，但当时桥对「写入未映射地址」是**静默拒绝**的——
> `handle_pdu` 里 FC05/06/0F/10 找不到段时直接 `return exc_pdu(fc, 0x02)`，
> **不写日志**（只有 MX 抛异常才会进 `[写失败]`）。
>
> 也就是说：如果 HMI 里地址仍是 `1x-*` 或填了表外地址，EBPro 收到异常码 02，
> 日志却一片空白——这就是"日志看着正常但按钮没用"的原因。
>
> **建议第一个改动**：在 `handle_pdu` 的四个写分支里补两行日志——
> 拒绝时打 `[写拒绝] 0x <addr>`，成功时打 `[写入] <软元件名>=<值>`。
> 这样按一次按钮就能立刻看清：请求有没有到桥、落在哪个软元件、有没有被拒。
> 这是排 P0 问题最快的抓手，成本 10 分钟。

**第 3 步：直接用 MX 测试工具验证 X 是否可写**

在装了 MX Component 的机器上跑一段最小脚本（32 位 Python）：

```python
from comtypes.client import GetModule, CreateObject
GetModule(r"C:\Program Files (x86)\MELSOFT\Common\ActUtlType\ActUtlType.tlb")
act = CreateObject("ActUtlType.ActUtlType")
act.ActLogicalStationNumber = 1
print("Open:", act.Open())
print("Write Y10:", act.SetDevice("Y10", 1))   # 期望 0 = 成功
print("Write X0 :", act.SetDevice("X0", 1))    # 这里是关键：非 0 就是仿真器拒绝
print("Read Y10:", act.GetDevice("Y10", 0))
```

**如果 X 确实写不进去**，方案 B（推荐，见下）可以绕开。

**第 4 步：确认没有梯形图/开关类型干扰**

- GX Works3 里对 X0/X1 有没有双线圈、`RST`、`PLS` 之类会立刻把它清掉的逻辑；
- EBPro 里 Toggle Switch 的动作模式是"交替（Toggle）"还是"瞬时（Momentary）"；如果是瞬时型，松手就回 0 是正常行为，不是 bug。

#### 建议的彻底方案（按优先级）

**方案 B（推荐）：让 HMI 全部用 0x，彻底不用 1x。**

0x 区是**可读可写**的（FC01 读、FC05 写），指示灯完全可以绑 0x：

```
x0 按钮 + x0 灯 → 都用 0x 10001
y10 按钮 + y10 灯 → 都用 0x 11009
M0 按钮 + M0 灯 → 都用 0x 1
```

好处：一个元件只有一个地址，不存在"写 0x / 读 1x"两套配置，也不会再出现绑错区导致的回弹。桥侧不用改任何代码（0x 本来就支持 FC01 读）。**建议直接改成这个用法，并在 README 里把 1x 标成"仅用于只读监控"。**

**方案 C：如果 MX 拒绝写 X/Y，就用 M 做按钮中转。**

桥增加一条映射规则（例如 0x 19001–20000 作为"M 中转区"），HMI 按钮写 M 区，梯形图里用 `LD M9000 → OUT X0` 的方式驱动。缺点是要改梯形图，优点是 100% 可靠。

**方案 D：桥侧做"写入即回读保持"。**

对 0x 镜像段写入后，桥在内存里记住该位的值，并在后续一段时间内对 1x 的读请求返回这个记忆值（而不是 PLC 的真实值）。这只在"PLC 确实不认这次写"时才有意义，属于掩盖问题，不推荐。

#### 需要向用户确认的信息

- 改完地址后，EBPro 里按下去是**完全没反应**，还是**闪一下又弹回**？（前者是写不进，后者是读回覆盖）
- 桥日志在按下瞬间有没有新增 `[写失败]` 行？
- GX Works3 的设备监控里，按下时 X0 / Y10 有没有变？

**这三条信息直接决定走方案 B/C/D 哪一条。**

#### 补充线索：注意画面上的 m0 开关（交接时用户的最新反馈）

用户最后传的画面里有 4 类元件：`x0`、`m0` 两个 Toggle Switch，`y10/y11/y12` 三个圆按钮（灯），反馈是"按钮有按不下去，也有按下去马上回弹"。

**关键点：M 区（0x 1–8000）是纯可写区，历史上已验证可用。如果连 `m0` 这个开关也按不下去，那就不是地址映射的问题**，而是 EBPro 侧的问题，优先查：

1. 元件是否真的绑到了"桥"这个 MODBUS TCP/IP 设备（不是别的设备/PLC 类型）；
2. EBPro 是否处于**模拟运行**模式（编辑模式下点按钮本来就没反应）；
3. 按钮是"Toggle Switch"还是"位状态切换"？"写地址"有没有填（有些元件只有读地址）；
4. 元件是否被安全/权限等级锁住，或放在被覆盖的图层上；
5. 是否勾了"使用系统寄存器"之类的选项，导致写入被本地逻辑吃掉。

判断方法：让用户在 EBPro 里同时监控 `m0` 和 `x0`。
- 两个都不动 → EBPro 配置问题（上面 5 条）；
- `m0` 能动、`x0` 不动 → 就是本文档讨论的 X/Y 写入问题，走方案 B/C。

> 📎 另注意和历史修复案例区分：**2026-11-17 修过一次"按钮动画回弹、灯不亮"**，
> 根因是 EBPro 32 字整块读跨分区边界（读回错位），与本章的写问题症状相似、根因不同。
> 详见交接文件夹里的《6_修复参考_跨段拆分.md》，那里有"先看 GX 软元件有没有变"的读/写分流判别法。

#### 6.1.1 v1.0.1 已落地的修复（2026-11-18）

代码侧确定性问题已修完，离线用例当时 20 项全过（`tests\test_offline.py`）：

| 修复 | 位置 | 说明 |
|---|---|---|
| FC16 数据偏移 | `mx_bridge.py` `handle_pdu` | `pdu[7+i*2]` → `pdu[6+i*2]`；旧版写单寄存器直接 `struct.error` 断连 |
| SetDevice 返回码 | `plc.write_bits/write_words` | 非 0 → Modbus 异常 04 + `[写失败]`，不再假成功 |
| 写入回读校验 | FC05 / FC06 | 回读不一致打 `[写入未生效]` |
| 写入日志 | FC05/06/0F/10 | `[写入]` / `[写拒绝]` / `[写失败]`，同时 echo 到 GUI 日志框 |
| FC15/FC16 校验 | 同上 | 长度、字节数校验，越界回异常 03 |
| 1x 地址提示 | `hint_area_mismatch` | 记住最近的 1x 读，发现「写 0x、读 1x」时打 `[地址提示]` |
| 地址表 | `main.py` `AddrMap.BAR` | X/Y 提到 `0x 10001 / 0x 11001`，换算器/速查表同步 |
| 端口探测 | `_probe_loop` | 移出主线程，修掉拖动卡顿 |
| 其它 | `Worker.call` 加锁、日志 2MB 轮转、安装包 `CloseApplications` | |

#### 6.1.2 v1.0.2：修「启动桥」按钮变灰、点不动（2026-11-18 用户验收时发现）

用户反馈「启动按钮按不了」：`▶ 启动桥` 是灰的，`■ 停止桥` 亮着，状态栏写「桥在运行，无数据」。

根因：`_refresh_buttons()` 用 `port_open()` 判断桥是否在跑 —— 只要 502 有人监听就禁用「启动桥」。
而桥是 `BridgeProc` 拉起的独立进程，GUI 被强杀或崩溃时子进程不跟着退，一直占着 502；
下次启动看到端口被占 → 禁用按钮 → 用户只能去任务管理器杀 python.exe。

本机实测确认占用者是：
`D:\Users\Wane\AppData\Local\Catact\python32\python.exe -u ...\mx_bridge.py --station 1 --port 502`
（旧安装目录版本留下的残留，父进程 32340 已不存在）。

修复：

1. `mx_bridge.py` 新增 `--parent-pid` 看门狗：**在连 MX 之前**就起线程，主程序退出后 1 秒内 `os._exit(0)`；
   （早期版本把线程放在 MX 连接之后，MX 连不上卡在重试时主程序已死、桥还赖着，已修正）
2. `_SafeOut` 包住 stdout/stderr：GUI 管道断开后 print 不再抛异常把 Modbus 连接带崩；
3. `main.py` 新增 `find_bridge_procs()` / `parse_proc_table()` / `classify_bridge_procs()`：
   - 父进程是 `Catact.exe` 一类 GUI 本体 → **另一个实例在用**，提示用户关掉那个窗口，绝不误杀；
   - 父进程已消失，或是 `python.exe / cmd.exe / powershell.exe` 等终端（手动跑出来的桥）→ **上次残留**，自动 `taskkill` 后继续启动；
   - 根本不是桥的进程 → 提示关掉它，或改 `config.json` 端口（如 1502）。
4. 「启动桥」只在**本进程的桥**运行时才禁用；「停止桥」在端口被占时也能点，用来清理；
5. 状态栏区分「桥在运行，无数据」和「端口 502 被占用（不是本程序的桥）· 点「启动桥」清理」。

离线用例同步扩到 25 项（`TestBridgeProcParsing`：残留 vs 另一个实例、别的端口、非 python 进程、
自己的桥要跳过、桥命令行必须带 `--parent-pid`）。

#### 6.1.3 真实写入验证（2026-11-18 11:36，开发机）

环境：GX Works3 仿真（FX5U）+ MX Component（逻辑站号 1）+ EBPro 在线，
直接对 `127.0.0.1:502` 发 Modbus：

| 请求 | 响应 | 回读 | 桥日志 |
|---|---|---|---|
| FC05 `0x 1` = 1 | 正常 | 1 | `[写入] 0x 1 → M0=1` |
| FC05 `0x 10001` = 1 | 正常 | 1 | `[写入] 0x 10001 → X0=1` |
| FC06 `4x 101` = 1234 | 正常 | 1234 | `[写入] 4x 101 → D100=1234` |

结论：**X 的 0x 镜像在 FX5U 仿真器上确实可写**，方案 B 成立；日志格式也按预期输出。
据此，用户侧剩下的变量只有 EBPro 里地址是否真的落到 0x（截图显示已改）。

---

### 6.2 【P1 · 未彻底解决】子窗口拖动仍被反映"卡"

用户前后提了三次："拖动有残影" → "拖动还是怪怪的" → "拖动起来还是好卡"。已做三轮改造：

| 轮次 | 做法 | 结果 |
|---|---|---|
| v3 | Canvas 自绘假窗口 | 有残影，跟不上鼠标 |
| v5 | 换成原生 `Toplevel` + `transient` | 残影没了，但仍"卡" |
| v6 | `<Configure>` 15ms 节流 + `SetWindowPos` 直移 + 子窗口自维护 `_target` | 有改善，用户仍觉得卡 |

**剩余可疑点（按可能性排序）：**

1. **主线程每 300ms 的 `_tick` 做了太多事**：`port_open()`（一次 `socket.create_connection`，超时 200ms，同步阻塞主线程！）+  drain 日志 + 遍历结果队列 + 更新状态标签 + `_refresh_buttons`。**`port_open` 在桥未启动时会阻塞 200ms，拖动时正好赶上一帧就明显掉帧。** 建议改成后台线程探测，主线程只读结果。
2. **`apply()` 里的 `.config()` 次数**：虽然有 `_last` 增量，但 400 格 × 多窗口，一轮下来仍是几百次 Tcl 调用。
3. **`transient()` 的副作用**：子窗口是 transient 时，Windows 会在 owner 移动/激活时重排 z-order，拖动主窗口会触发额外的窗口管理开销。可以试 `wm_attributes("-toolwindow", True)` 或去掉 transient 改用 `wm_group`。
4. **每格一个 `Label`**：400 个 widget 本身就重。彻底方案是改成 **Canvas 批量绘制**（一次 `create_rectangle` + `itemconfig` 只改变化的 item），或只渲染可见的 ~160 格。

**验证手段**：`_dragtest.py` 会把主窗口平移 (120, 90) 并读子窗口坐标，可用来确认跟随是否精确（当前 PASS，说明是性能问题不是逻辑问题）。

---

### 6.3 其它已知问题（P1/P2）

| # | 问题 | 影响 | 建议 |
|---|---|---|---|
| 1 | `Plc` 对象无锁，多客户端并发时多个 `client_worker` 线程会同时调 `Worker.call` | 高并发下可能数据错乱或超时 | `Worker.call` 加 `threading.Lock`（成本极低，建议直接加） |
| 2 | 写多线圈/多寄存器是**逐点** `SetDevice` | 写 100 个点 = 100 次 COM 调用，可能几百 ms | 改用 `WriteDeviceBlock`（与 `ReadDeviceBlock` 对称，需同样手工 Invoke） |
| 3 | `ZR` 仿真器不支持 | 读会抛异常 → 返回 Modbus 异常码 04 | 已在 README 注明；或从表里移除让读返回 0 |
| 4 | `modbus_debug.log` 无轮转 | 长期运行无限增长（当前 98KB） | 按大小切分或只在有错误时写 |
| 5 | 安装包**覆盖升级会失败**（exit code 5） | 用户需先卸载再装 | 在 `[Setup]` 加 `CloseApplications=yes`，或安装前检测进程 |
| 6 | PyInstaller `--onefile` 启动 3–5s（解压到 temp） | 双击后要等 | 改 `--onedir`（目录版启动 <1s，体积也差不多） |
| 7 | 无自动化测试 | 改地址表容易踩回归 | 把 `_mirrortest.py` 变成正式 pytest，覆盖 16 种元件的双向换算 |
| 8 | UI 从后台/自动化环境启动时窗口会被系统强制最小化 | 仅影响脚本化启动，用户双击无此问题 | 无需处理；如需自动化启动，用 `SetWindowPlacement(showCmd=SW_SHOWNORMAL)` 恢复 |

---

## 7. 调试工具与方法

| 脚本 | 位置 | 用途 |
|---|---|---|
| `_shot.py` | `C:\Users\Wane\WorkBuddy\2026-11-16-00-46-45\` | 按窗口标题抓图（`PrintWindow` + `PW_RENDERFULLCONTENT`，已声明 DPI 感知）。用法：`py -3 _shot.py "Catact" out.png` |
| `_dragtest.py` | 同上 | 用 `SetWindowPos` 平移主窗口，验证子窗口跟随位移是否精确 |
| `_mirrortest.py` | 同上 | 离线单元测试：stub 掉 MX，验证映射换算 / 跨段拆分 / 写入路由 |
| `地址对照表.html` | 项目根 | 浏览器里查地址（打印友好） |

**常用诊断命令**

```bash
# 502 端口占用 / 谁在连
netstat -ano | grep ":502 "

# 仿真器是否在跑（也是看门狗的判断依据）
tasklist /FI "IMAGENAME eq FSimRun3.exe"

# 桥日志（32 位进程把它写在 mx_bridge.py 同目录）
tail -f app/modbus_debug.log

# 窗口物理尺寸 / DPI 是否真的生效
py -3 -c "import ctypes,ctypes.wintypes as wt;u=ctypes.windll.user32;u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))"
```

---

## 8. 构建与打包

### 8.1 打 GUI 单文件

```bat
cd /d "D:\Project folder\删掉\91\软件制作文件夹\MXBridgeTool"
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name Catact --icon app\catact.ico app\main.py
```

产物 `dist\Catact.exe`。**注意**：exe 运行时会从 `sys.executable` 所在目录找 `mx_bridge.py` 和 `python32\`，所以必须和这两个放同一目录（`release\Catact\` 就是这个结构）。

### 8.2 组装便携版

```
release\Catact\
├─ Catact.exe        ← dist 里复制过来
├─ mx_bridge.py      ← app 里复制（两边必须一致！）
├─ catact.ico
├─ README.txt
├─ python32\         ← app\python32 整目录复制
└─ 启动.bat          ← 便携版启动器（start "" Catact.exe）
```

### 8.3 打安装包

```bat
"/c/Program Files (x86)/Inno Setup 6/ISCC.exe" Catact.iss
```

`Catact.iss` 要点：`PrivilegesRequired=lowest`（装到 `{localappdata}\Catact`，免管理员，config 可写）、简体中文向导、可选桌面快捷方式、卸载器自带。

**改代码后的重打包顺序**（务必按这个来，否则 exe 与脚本版本不一致）：

```
改 app\main.py 或 app\mx_bridge.py
  → PyInstaller 重打 Catact.exe
  → 复制到 release\Catact\（同时复制 mx_bridge.py）
  → ISCC 重打安装包
  → 出便携版 zip
```

---

## 9. 后续优化建议（按优先级）

| 优先级 | 事项 | 理由 |
|---|---|---|
| **P0** | 按 6.1 的四步验证按钮问题，确定走方案 B/C | 这是用户当前唯一挡路的问题 |
| **P0** | `Worker.call` 加锁 | 一行代码，消除并发崩溃风险 |
| **P1** | HMI 统一用 0x，README 把 1x 降级为"只读监控" | 消除"绑错区"这一类问题的所有变种 |
| **P1** | `port_open()` 移出主线程 | 直接改善拖动流畅度（6.2 第 1 点） |
| **P1** | 监视窗口改 Canvas 批量绘制 | 彻底解决大数据量下的重绘开销 |
| **P2** | `WriteDeviceBlock` 批量写 | 多线圈/多寄存器写入提速 |
| **P2** | 日志轮转 + 安装包覆盖升级修复 | 交付体验 |
| **P2** | 补 pytest（把 `_mirrortest.py` 正式化） | 防地址表回归 |
| **P3** | 支持 FC17（读写组合）、float/32 位寄存器 | 更完整的 Modbus 兼容性 |

---

## 10. 交付物与验收清单

### 10.1 本次交付（v1.0.2）

| 交付物 | 路径 | 说明 |
|---|---|---|
| **便携版（免安装）** | `2_Catact_1.0.2_免安装版.zip` | 28.8 MB，解压即用，根目录 `Catact\` |
| **安装包** | `3_Catact_1.0.2_安装包.exe` | 28.8 MB，装到 `%LOCALAPPDATA%\Catact` |
| 构建产物（源目录） | `MXBridgeTool\release\Catact_1.0.2_便携版.zip`、`MXBridgeTool\installer\Catact_Setup_1.0.2.exe` | `build_release.py` 直接产出，与上面同一份 |
| 用户说明 | `4_用户使用说明.txt`（副本：`MXBridgeTool\README.txt`、`release\Catact\README.txt`） | 含日志标签速查 |
| 本次修复说明 | `6_本次修复说明.txt` | 给用户的自测步骤 |
| 本交接报告 | `1_Catact交接报告.md`（副本：`MXBridgeTool\交接报告.md`） | |

校验值（sha256，2026-11-18 11:49 最终重新打包后实测）：

```
2_Catact_1.0.2_免安装版.zip   b962003015dccb8e53518a81a2483dfcf101ddccaf6162be881e50f17911bce7
                              30,155,210 字节（28.8 MB，1345 项，根目录 Catact\）
3_Catact_1.0.2_安装包.exe     42e6423078030fd98e01be6b4d9a4d5808e7fa59c2cdf82a63770f50b8417823
                              30,137,766 字节（28.7 MB），与 installer\Catact_Setup_1.0.2.exe 一致
Catact.exe（打包进 zip）      7617c873c1a6c0bc7bdec46bccf2ea5481defd2f1f074bbee84f02ebff4610fe
                              11,363,642 字节，与 dist\Catact.exe 一致
mx_bridge.py（app 与 release）d30878da729f6136678fbad55f4aebc7246961ac2ca60553a79a114b22bbf538
                              31,315 字节，两份完全一致
```

### 10.2 验收清单（新接手人自测用）

标注 ✅ 的项，本次已在开发机上实测通过；其余项依赖 GX Simulator / MX Component / EBPro 现场环境，必须由用户在装有 MELSOFT 的电脑上验证。

- [x] ✅ 解压便携版 → 双击 `启动.bat` → 主窗口出现，标题栏是猫图标 + "Catact"，文字清晰无发虚（已实测解压 + 启动）
- [x] ✅ 点元件 `M` / `X` / `Y` → 监视窗口弹出（标题 `M0–399（400 点）`、`X0–307（200 点）`、`Y0–307（200 点）`）
- [ ] 拖动主窗口时子窗口跟随（需人工手感确认）
- [ ] 启动 GX 仿真（FX5U，RUN）→ 点「启动桥」→ 状态灯变绿
- [ ] 监视窗口里 M0 与 GX Works3 设备监控里的 M0 一致（用 GX 强制置 1 验证）
- [ ] EBPro 连 127.0.0.1:502 能读到数据（指示灯亮）
- [ ] EBPro 写 M0 = 1 → GX 梯形图里 M0 导通（验证写链路）
- [ ] **按钮问题**：按 6.1.1 四步验证（HMI 地址改成 `0x 10001 / 0x 10002 / 0x 11009`，按一次，看日志有没有 `[写入]` / `[写入未生效]` / `[地址提示]`）

已在本机通过的自动化验证：

- `MXBridgeTool\tests\test_offline.py`：25 个离线用例全部通过（FC16 偏移、FC05/06 回读校验、日志标签、地址提示、桥进程识别）
- 地址映射核对：`X0 → 0x 10001`、`X1 → 0x 10002`、`Y10 → 0x 11009`、`M0 → 0x 1`、`D100 → 4x 101`
- 便携版 exe 启动后界面为 1.0.2：地址速查里 X/Y 显示 `0x 10001 / 0x 11001`
- **v1.0.2 清理路径（in-process 实测）**：先用一个「父进程已死」的假桥占住 502，
  再启动 GUI → `▶ 启动桥` 状态为 `normal`（可点）、`■ 停止桥` 也为 `normal`；
  调 `start_bridge()` 后日志依次出现
  `[清理] 结束上次残留的桥进程 PID 30872` → `✓ 桥已启动` → `[桥] Modbus TCP 已启动 127.0.0.1:502`
- **v1.0.2 关闭联动（实测）**：GUI 被 `taskkill /F` 强杀后 1 秒内桥自己退出，502 释放
  （旧版此场景必然留下占端口的 `python.exe`，正是按钮变灰的成因）

---

## 11. 交接注意事项

1. **`app\python32\` 不能删**。桥必须用 32 位 Python（MX Component 是 32 位 COM）。目录里已装好 pywin32 + comtypes，是 embeddable 版本。
2. **`mx_bridge.py` 有两份副本**：`app\`（开发用）和 `release\Catact\`（便携版用）。改了记得同步（本报告 8.3 有顺序）。
3. **路径含中文和空格**（`D:\Project folder\删掉\91\软件制作文件夹\`）。所有脚本都用 `%~dp0` 或绝对路径，别用相对路径拼接；PowerShell 里直接引用要加引号。
4. **`config.json` 自动生成**（在 `APP_DIR` 下），存 host/port/station/refresh_ms/python32 路径，不进版本管理。
5. **用户的实际使用环境**：Windows 10/11 x64、2560×1440 @125%、EBPro + GX Works3 + MX Component 都装在开发机本地，EBPro 与桥同机（127.0.0.1）。
6. **和用户沟通时要问"按下是没反应还是弹回"**——这一个问题就能把根因分成两半（写不进 vs 读回覆盖），比看代码快得多。
7. **不要在用户没改 HMI 地址的情况下继续改代码**。当前 P0 问题有一半概率只是 HMI 工程里地址没改。

---

## 附录 A：用户视角的地址速查

```
M0    → 0x 1          X0   → 1x 1      /  写：0x 10001
M10   → 0x 11         X1   → 1x 2      /  写：0x 10002
S0    → 0x 8001       Y10  → 1x 1009   /  写：0x 11009
B0    → 0x 9001       Y0   → 1x 1001   /  写：0x 11001
D100  → 4x 101        T5   → 1x 2006   /  当前值 4x 9006
W1F   → 4x 8032       C3   → 1x 3004   /  当前值 4x 10004
```

**判断口诀：能按的用 0x / 4x，只看状态的用 1x。**
