# 应用图标规范（frontend/build）

本目录用于存放 MiniClaw 桌面应用的图标资源。约定如下。

## 1. 现在的 UI（未打包时）

窗口 / 任务栏图标由 `electron/main.js` 的 `resolveWindowIcon()` 决定，查找顺序：

1. `frontend/build/icon.ico`（Windows 首选）
2. `frontend/build/icon.png`

把图标按上述名字放进本目录即可生效（改 `electron/main.js` 需重启应用）。

## 2. 图标尺寸规格

### 2.1 Windows —— `.ico`（你已制作的文件）

`.ico` 是「多尺寸容器」，一个文件里应包含以下尺寸（自上而下推荐顺序）：

| 尺寸 | 用途 |
| --- | --- |
| 16×16 | 任务栏小图标、列表、菜单 |
| 24×24 | 任务栏、部分场景小图标 |
| 32×32 | 任务栏、Alt+Tab 切换 |
| 48×48 | 桌面快捷方式、资源管理器 |
| 64×64 | 中等尺寸显示 |
| 128×128 | 大图标视图 |
| 256×256 | 超大图标 / 高 DPI 缩放 |

- **最低要求**：至少包含 `16、32、48、256` 四个尺寸。
- **256×256** 必须以 **32 位 PNG 压缩**格式嵌入（不要用 BMP），否则文件过大或不被识别。
- 其余尺寸用 32 位（含 Alpha 透明通道）即可，BMP 或 PNG 均可。
- 单个 `.ico` 文件通常控制在 **≤ 1 MB**。

### 2.2 macOS —— `.icns`（打包 macOS 时需要）

用 **1024×1024 的 PNG** 作为源图生成 `.icns`，其中应包含：

| 逻辑尺寸 | 倍图文件 |
| --- | --- |
| 16×16 | icon_16x16 + icon_16x16@2x(32) |
| 32×32 | icon_32x32 + icon_32x32@2x(64) |
| 128×128 | icon_128x128 + icon_128x128@2x(256) |
| 256×256 | icon_256x256 + icon_256x256@2x(512) |
| 512×512 | icon_512x512 + icon_512x512@2x(1024) |

即实际像素集合：16 / 32 / 64 / 128 / 256 / 512 / 1024。

### 2.3 Linux —— PNG 集合（打包 Linux 时需要）

提供一组 PNG（放 `frontend/build/icons/`，命名如 `16x16.png`）：

16×16、24×24、32×32、48×48、64×64、128×128、256×256、512×512。

## 3. 打包 / 部署时准备哪些

| 目标平台 | 需要的文件 | 放在这里 |
| --- | --- | --- |
| Windows | `icon.ico`（含上述 16–256 全套） | `frontend/build/icon.ico` |
| macOS | `icon.icns` | `frontend/build/icon.icns` |
| Linux | `icons/*.png`（16–512） | `frontend/build/icons/` |

> 打通用包时，只要有一个 **1024×1024 的 PNG 源图**，多数打包工具能自动生成 macOS/Linux 所需尺寸；但 **Windows 必须提供真正的多尺寸 `.ico`**（不能用 PNG 代替）。
> 打包工具（如 electron-builder）默认读取本 `build/` 目录作为 `buildResources`。

## 4. 应用内（favicon / 标题栏 logo，可选）

- 浏览器标签页 favicon：32×32（附带 16×16）。
- 标题栏 logo：20–32px 高度的 PNG/SVG。

## 5. 一键生成（make_icon.py）

把方形源图放到 `frontend/build/icon-src.png`，然后运行：

```bash
python frontend/build/make_icon.py
# 或指定源图：python frontend/build/make_icon.py path/to/source.png
```

生成物：

| 文件 | 内容 |
| --- | --- |
| `icon.ico` | Windows 多尺寸图标（16/24/32/48/64/128/256，LANCZOS 缩放，32 位） |
| `icon.png` | 256×256，未打包时窗口图标回退使用（`electron/main.js`） |
| `icons/*.png` | Linux 打包用 PNG 集合（16…512，超过源图尺寸的自动跳过） |

### 源图尺寸建议

- **≥ 256×256**：可生成 Windows 全套 `.ico`（16–256）。
- **≥ 512**：可兼顾 Linux 的 512 PNG。
- **1024×1024**：最佳，可一步覆盖 Windows / macOS / Linux 全部尺寸。
- 源图请保持**方形、透明背景**，图形四周预留约 10% 安全边距，避免小尺寸被裁切。
- 若源图小于目标尺寸，脚本会**跳过大尺寸**（不做放大，避免模糊）。
