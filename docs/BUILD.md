# 构建与运行环境

## 1. 两种 Python

| 用途 | 位数 | 版本 | 依赖 |
|---|---|---|---|
| GUI `app/main.py` | 64 位 | 3.10+ | 标准库 |
| 桥 `app/mx_bridge.py` | **32 位** | 3.12 | `comtypes`、MX Component |

GUI 用 64 位打包成 `Catact.exe`；桥必须用 32 位 Python，因为 `ActUtlType` 是 32 位 COM 组件。

## 2. 准备 32 位桥运行时

### 方式 A：放到默认目录（推荐）

安装 32 位 Python 3.12，然后：

```powershell
C:\Path\To\Python312-32\python.exe -m pip install -r requirements.txt
```

把整个 32 位 Python 目录复制到：

```
app\python32\
```

确保存在：

```
app\python32\python.exe
app\python32\Lib\site-packages\comtypes\
```

`app/python32` 已在 `.gitignore` 中排除，不会进入 Git；打包时 `build_release.py` 会自动复制到 `release\Catact\python32`。

### 方式 B：用系统已装的 32 位 Python

启动一次 GUI，关闭后编辑 `app\config.json`：

```json
{
  "python32": "C:\\Path\\To\\Python312-32\\python.exe"
}
```

必须是绝对路径。GUI 每次启动都会读 `app/config.json`。

## 3. 安装 64 位构建依赖

```powershell
py -3 -m pip install pyinstaller
```

`build_release.py` 还需要 Inno Setup 6（可选，不打安装包可以跳过）：

```
C:\Program Files (x86)\Inno Setup 6\ISCC.exe
```

如果路径不同，改 `build_release.py` 里的 `ISCC` 常量。

## 4. 跑测试

在仓库根目录：

```powershell
py -3 tests\test_offline.py
py -3 tests\test_gui_state.py
py -3 tests\test_gui_layout.py
py -3 tests\test_gui_bridge_flow.py
```

`test_gui_bridge_flow.py` 会用 1502 端口真实启动桥；确保 1502 没被占用。GX 仿真开着时它会走“已连接”分支，属于正常。

## 5. 打包

```powershell
py -3 build_release.py
```

流程：

1. 跑 `test_offline.py`
2. PyInstaller 打 `dist\Catact.exe`
3. 组装 `release\Catact\`（exe + mx_bridge.py + python32 + README + ico）
4. Inno Setup 打 `installer\Catact_Setup_<ver>.exe`
5. 打 `release\Catact_<ver>_便携版.zip`，并复制到仓库上一级为 `2_Catact_<ver>_免安装版.zip`

版本号在三个地方同步：

- `app/main.py` 的 `APP_VERSION`
- `build_release.py` 的 `VER`
- `Catact.iss` 的 `AppVersion` / `AppVerName` / `OutputBaseFilename`

打包前确认这三处一致。

## 6. 常见问题

**找不到 32 位 Python**

GUI 点启动会提示 `找不到 32 位 Python`。检查 `app\python32\python.exe` 是否存在，或 `config.json` 的 `python32` 是否指向真实 exe。

**comtypes 缺失**

用 32 位 Python 执行：

```powershell
python.exe -m pip install comtypes
```

**MX Component 未安装**

Catact 右侧「MX 环境」会显示未检测到。安装 MX Component 后点「重新检测」，或手动「定位...」选择 `ActComm.exe`。
