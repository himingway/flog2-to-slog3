# LUT → Adobe Camera Raw Style Converter

将视频 Log 3D LUT（Sony S-Log3、Fujifilm F-Log2 等）重烘为 **Adobe Camera Raw（Apply LUT）** 可直接使用的 **Style LUT**：只保留色相与饱和度风格，维持 RAW 显影原有的明暗与对比。

## 特性

- **面向 ACR 接口重烘**：按 ACR Apply LUT 所用的 sRGB/Rec.709 伽马空间编码，输出 **64³** 标准 `.cube`（四面体插值，8 位小数）。
- **保亮度色域收缩**：在线性光下将 LUT 输出亮度替换为输入图像亮度；高饱和越界颜色沿等亮度灰轴向中性灰回缩，避免逐通道硬截断引起的偏色与亮度跌落。
- **双源链路**：
  - `lut_to_acr.py`：Sony `S-Log3 / S-Gamut3.Cine` 源 LUT 通用转换（支持多空间/影调选项）。
  - `build_fuji_style.py`：基于 `colour-science` 批量处理富士官方 `F-Log2 / F-Gamut` 胶片模拟包（自动跳过 `FLog2-709`、`WDR` 等非显示级技术曲线）。

## 转换链路（Style 模式）

1. ACR 输入 sRGB 码值 → 解码为线性 RGB
2. 转换到源 LUT 期望空间（`S-Gamut3.Cine → S-Log3` 或 `F-Gamut → F-Log2`）
3. 四面体插值采样原始 LUT
4. 解码到线性光，按 Rec.709 亮度权重保留输入亮度并做等亮度色域收缩
5. 编码回 sRGB 码值写出 64³ `.cube`

## 快速开始

### 1. 安装依赖

```bash
uv sync
# 或: pip install -r requirements.txt
```

### 2. 转换 LUT

```bash
# 单个 S-Log3 LUT → ACR Style LUT
python3 lut_to_acr.py --space srgb --tone preserve --size 64 \
    input.cube "output/acr_style/My Look Style.cube"

# 批量重建富士官方包（输出 10 个胶片模拟）
.venv/bin/python build_fuji_style.py

# 若本地已放入 sources/sony_luts/*.cube，可一键全量重建
./rebuild_all.sh
```

常用参数（`lut_to_acr.py`）：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--tone` | `lut` | `preserve`（保亮度仅留色风） / `lut`（保留原 LUT 影调） |
| `--space` | `srgb` | 输入/输出目标空间（`srgb`、`adobergb`、`prophoto-gamma` 等） |
| `--display-gamma` | `srgb` / `2.4` | 源 LUT 输出的显示解码曲线（`srgb`、`2.4`、`2.2`、`bt709-oetf`） |
| `--size` | `64` | 输出网格精度（2–64，Camera Raw 上限为 64） |
| `--interp` | `tetrahedral` | 源表采样插值方式（`tetrahedral` / `trilinear`） |

### 3. 导入 Camera Raw

将生成的 `.cube` 复制到 Camera Raw LUT 目录（或运行 `./redeploy_to_acr.sh`，支持自动识别 WSL/macOS 目录或手动传入路径），**完全退出并重启** Photoshop / Camera Raw 后在「颜色分级 → 应用 LUT」中选用：

- **Windows**: `%APPDATA%\Adobe\CameraRaw\Settings\LUTs`
- **macOS**: `~/Library/Application Support/Adobe/CameraRaw/Settings/LUTs`

> 注意：Camera Raw 菜单读取 `.cube` 内的 `TITLE` 字段而非文件名（脚本已自动令二者一致），且仅识别 **≤ 64³** 格点的 3D LUT。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## 目录结构

```text
lut_convert/
├── lut_to_acr.py         # 主转换器（S-Log3 / S-Gamut3.Cine → ACR）
├── build_fuji_style.py   # 富士官方 F-Log2 包批量构建脚本
├── rebuild_all.sh        # 清理并全量重建脚本
├── redeploy_to_acr.sh    # 部署 .cube 到 Camera Raw 并清索引缓存
├── tests/                # 单元测试与输出 LUT 校验
├── sources/              # 源 LUT（官方 Fuji 包及自备 Sony/第三方 LUT）
├── output/               # 生成结果（acr_style/ 与 not_deployed/）
└── legacy/               # 历史版本（F-Log2 → S-Log3 转换器）
```
