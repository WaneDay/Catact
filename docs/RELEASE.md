# Release 发布流程

## 1. 版本号

同步修改：

- `app/main.py`：`APP_VERSION = "1.0.x"`
- `build_release.py`：`VER = "1.0.x"`
- `Catact.iss`：`AppVersion` / `AppVerName` / `OutputBaseFilename`

## 2. 打包

```powershell
py -3 build_release.py
```

得到：

```
dist\Catact.exe
release\Catact\Catact.exe
release\Catact_<ver>_便携版.zip
installer\Catact_Setup_<ver>.exe
..\2_Catact_<ver>_免安装版.zip
```

## 3. 整理 Release 资产

在仓库外新建一个临时发布目录，统一命名：

```
Catact_Setup_<ver>.exe          ← 常规安装包
Catact_<ver>_Portable.zip       ← 绿色免安装
Catact_<ver>_Source.zip         ← 源码快照（可选，GitHub 也会自动生成）
Catact_<ver>_Bundle.zip         ← 大包：安装包 + 绿色版 + README + SHA256
SHA256SUMS.txt                  ← 校验和
```

`Bundle` 只装发布物，不装源码：

```
Catact_<ver>_Bundle.zip
├─ Catact_Setup_<ver>.exe
├─ Catact_<ver>_Portable.zip
├─ README.md
├─ RELEASE_NOTES_<ver>.md
└─ SHA256SUMS.txt
```

生成校验和（PowerShell）：

```powershell
Get-FileHash Catact_Setup_<ver>.exe -Algorithm SHA256
Get-FileHash Catact_<ver>_Portable.zip -Algorithm SHA256
Get-FileHash Catact_<ver>_Bundle.zip -Algorithm SHA256
```

把结果写进 `SHA256SUMS.txt`。

## 4. 创建 Release

用 GitHub CLI：

```powershell
gh release create v<ver> `
  --title "Catact v<ver>" `
  --notes-file docs/RELEASE_NOTES_<ver>.md `
  Catact_Setup_<ver>.exe `
  Catact_<ver>_Portable.zip `
  Catact_<ver>_Bundle.zip `
  SHA256SUMS.txt
```

如果还没登录：

```powershell
gh auth login --hostname github.com --git-protocol https --web
```

## 5. 发布后检查

- Release 页面能下载 4 个资产：安装包、绿色版、大包、校验和
- `Catact_<ver>_Portable.zip` 解压后没有 `config.json`、`modbus_debug.log`
- 安装包安装到 `%LOCALAPPDATA%\Catact`，不覆盖用户已有配置
- `README.md` 里的图片能正常显示
- Tag 的源码和 Release 源码一致

## 6. 更新包适配

安装包使用固定 `AppId`：

```
{{7E2A9C41-5B3D-4F8A-9C6E-1D24A8B3F5C7}
```

新版本直接覆盖安装到同一目录，Inno Setup 会保留 `config.json`（安装脚本不包含该文件）。升级前建议关闭 Catact 和桥，避免文件占用。
