# Catact v1.0.6

GX Works3 FX5U 仿真器 ⇄ 威纶通 EBPro 的 Modbus TCP 桥。

## 这个版本

- 默认中文界面，`选项 → 语言 → English` 可切回原来的英文
- 中文使用 Microsoft YaHei UI 9（找不到时回退微软雅黑 / 宋体 / Segoe UI）
- 语言保存到 `config.json`，切换后自动重启
- 桥逻辑沿用 1.0.4/1.0.5：仿真重启自动重连，按钮互斥，手动重连兜底

## 下载哪个

| 文件 | 用途 |
|---|---|
| `Catact_Setup_1.0.6.exe` | 常规安装包，安装到 `%LOCALAPPDATA%\Catact`，带桌面快捷方式 |
| `Catact_1.0.6_Portable.zip` | 绿色免安装，解压后双击 `Catact.exe` |
| `Catact_1.0.6_Bundle.zip` | 大包：安装包 + 绿色版 + 本说明 + SHA256，适合离线拷贝 |
| `Catact_1.0.6_Source.zip` | 源码快照；也可以直接用 GitHub 的 Source code |
| `SHA256SUMS.txt` | 校验和 |

免安装版已内置 32 位 Python，不需要另装 Python。

## 快速使用

1. 安装 GX Works3（含 GX Simulator3）、MX Component、威纶通 EBPro。
2. GX Works3 打开 FX5U 工程 → 点「模拟开始/停止」。
3. 管理员运行 Communication Settings Utility → Wizard：
   - Logical station `1`
   - PC side I/F `GX Simulator3`
   - CPU `FX5U`
   - Port `0` / System `1` / PLC `1` / Timeout `10000 ms`
4. EBPro → 系统参数 → 新增设备：
   - `MODBUS TCP/IP`
   - `127.0.0.1:502`
   - 站号 `1`
5. 打开 Catact → 「▶ 启动」→ 状态栏「已连接」。
6. EBPro 开关地址用 `0x`：`X0 → 0x 10001`；`1x 10001` 是只读，开关不要绑。

完整图文教程见仓库 README。

## 已知限制

- 默认只监听 `127.0.0.1:502`，EBPro 必须和 Catact 在同一台电脑；跨电脑/虚拟机需要改 `config.json` 的 `host`，当前 GUI 没有 host 设置项。
- 需要 Windows 10/11 64 位；MX Component 必须是 32 位运行环境。
- 不含 GX Works3、MX Component、EBPro，需要自行安装。
- 语言切换会重启 Catact 并停止当前桥，重启后需再点一次「▶ 启动」。
