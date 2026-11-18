# app/python32

这个目录用于放置 **32 位 Python 3.12 + comtypes**，供 `mx_bridge.py` 使用。

仓库不提交这个运行时（约 30 MB 的第三方二进制），请按 [`../../docs/BUILD.md`](../../docs/BUILD.md) 准备。

目录结构应类似：

```
app/python32/
├─ python.exe
├─ python312.dll
├─ Lib/site-packages/comtypes/
└─ ...
```

GUI 会默认读取 `app/python32/python.exe`；也可以在 `app/config.json` 的 `python32` 里指定其他绝对路径。
