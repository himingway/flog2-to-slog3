# F-Log2 to S-Log3 & Camera Raw Style LUT Toolkit

包含两套面向 Sony / RAW 摄影用户的 3D `.cube` LUT 工具链（均基于四面体插值）：

1. **F-Log2 → S-Log3 / S-Gamut3(.Cine)**（[`fuji_to_sony_lut.py`](fuji_to_sony_lut.py)）：将富士官方 F-Log2 胶片模拟 LUT 转为 Sony S-Log3 视频 LUT，供 DaVinci Resolve 与相机机内监看使用。
2. **Camera Raw / Lightroom Classic Style LUT**（[`lut_to_acr.py`](lut_to_acr.py) 及批量构建器与原创 OKLab LUT）：生成 Adobe Camera Raw（Apply LUT）可用的 **64³ 严格保亮度风格 LUT**——只塑造色彩与分离色调，保持 RAW 显影原有的线性明暗与动态范围。

## 安装依赖

```bash
uv sync
# 或: pip install -r requirements.txt
```

---

## 一、F-Log2 → S-Log3 / S-Gamut3(.Cine)（视频工作流）

链路：`S-Log3 解码 → S-Gamut3(.Cine) → F-Gamut（Bradford）→ F-Log2 编码（保留负值延拓）→ 四面体采样原 LUT`

```bash
# 默认读取 sources/fuji_official，输出到 output/Sony_SLog3_Converted_fuji_official/
.venv/bin/python fuji_to_sony_lut.py

# 指定输入色域与输出网格精度
.venv/bin/python fuji_to_sony_lut.py \
    -i ./sources/fuji_official \
    --input-colourspace S-Gamut3.Cine \
    --output-grid-size 65
```

| 参数 | 默认值 | 说明 |
|---|---|---|
| `-i, --input` | `./sources/fuji_official` | 富士官方 LUT 目录（仅处理 `FLog2_to_*`） |
| `-o, --output` | `output/Sony_SLog3_Converted_<名>` | 输出目录 |
| `--input-colourspace` | `S-Gamut3.Cine` | `S-Gamut3.Cine` 或 `S-Gamut3` |
| `--output-grid-size` | `auto` | 保留源分辨率（33/65）或指定 `33` / `65` / `129` |

---

## 二、Adobe Camera Raw Style LUT（RAW 摄影工作流）

转换链路：`ACR sRGB 输入 → 线性 → S-Log3 / F-Log2 / ARRI LogC3 / LogC4 → 四面体采样（含可选 Look Library 串联与 EV 偏移）→ 解码并替换为输入线性亮度（越界高饱和沿等亮度灰轴内缩）→ 编码回 sRGB 64³`

```bash
# 单个 S-Log3 LUT → ACR Style LUT
.venv/bin/python lut_to_acr.py --space srgb --tone preserve --size 64 \
    input.cube "output/acr_style/My Look Style.cube"

# 批量构建富士官方 F-Log2 胶片模拟（自动跳过 FLog2-709 / WDR 技术曲线）
.venv/bin/python build_fuji_style.py

# 批量构建 ARRI 官方 LogC3/LogC4（REVEAL、Alexa Classic、ALF2 与 Look Library）
# 官方下载：https://www.arri.com/en/learn/camera-systems/technical-downloads
.venv/bin/python build_arri_style.py

# 批量构建 Sony VENICE 官方 Look（s709 / Look 7525 / Look 1）
# 官方下载：https://sony-cinematography.com/resources/luts/
.venv/bin/python build_film_style.py

# 批量构建精选索尼 S-Log3 风格包（统一添加 "Sony26 " 菜单前缀，含 Quirky_33x 的 +0.5 EV 校准）
.venv/bin/python build_sony26_style.py

# 生成两支原创 OKLab 分区可微保亮度 LUT（CrystalFilm 通透轻胶片 & AnalogFilm 浓郁光学胶片）
.venv/bin/python build_ultimate_style.py

# 一键全量重建并部署到 Camera Raw（支持 WSL/macOS 自动定位或手动传参）
./rebuild_all.sh
./redeploy_to_acr.sh
```

`lut_to_acr.py` 常用参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--tone` | `lut` | `preserve`（保亮度仅留色风） / `lut`（保留原 LUT 影调） |
| `--space` | `srgb` | 目标接口空间（`srgb`、`adobergb`、`prophoto-gamma` 等） |
| `--display-gamma` | `srgb` / `2.4` | 源 LUT 输出的显示解码曲线（`srgb`、`2.4`、`2.2`、`bt709-oetf`、`linear`） |
| `--ev-offset` | `0.0` | 输入 S-Log3 查表前的曝光偏移 EV（如校准 ETTR LUT） |
| `--size` | `64` | 输出格点数（2–64，Camera Raw 上限为 64） |
| `--interp` | `tetrahedral` | 插值方式（`tetrahedral` / `trilinear`） |

> Camera Raw 说明：Apply LUT 菜单读取 `.cube` 内的 `TITLE` 而非文件名，仅识别 **≤ 64³** 格点；部署到 `%APPDATA%\Adobe\CameraRaw\Settings\LUTs`（Win）或 `~/Library/Application Support/Adobe/CameraRaw/Settings/LUTs`（macOS）后需完全重启 PS / Camera Raw。

---

## 测试与目录结构

```bash
.venv/bin/python -m unittest discover -s tests -v
```

```text
lut_convert/
├── fuji_to_sony_lut.py     # ① F-Log2 → S-Log3 / S-Gamut3(.Cine)（视频）
├── lut_to_acr.py           # ② S-Log3 → Adobe Camera Raw Style（RAW 核心转换）
├── build_fuji_style.py     # ② 富士官方 F-Log2 → Camera Raw Style（10 款）
├── build_arri_style.py     # ② ARRI 官方 LogC3/LogC4 → Camera Raw Style（10 款）
├── build_film_style.py     # ② Sony VENICE Look → Camera Raw Style（3 款）
├── build_sony26_style.py   # ② Sony26 精选胶片/人像/通透包 → Camera Raw Style（23 款）
├── build_ultimate_style.py # ② 原创 OKLab 配方：CrystalFilm & AnalogFilm（2 款）
├── rebuild_all.sh          # ACR Style 一键清理与全量重建
├── redeploy_to_acr.sh      # 部署 output/acr_style/*.cube 到 Camera Raw 并清索引缓存
├── tests/                  # 单元测试与产出完整性校验
├── sources/                # 源 LUT（官方 Fuji 包由 git 跟踪；其余大包本地忽略）
└── output/                 # 生成结果（acr_style / not_deployed / slog3_converted，不入库）
```
