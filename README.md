# F-Log2 to S-Log3 & Camera Raw Style LUT Toolkit

包含两套面向 Sony / RAW 摄影用户的 3D `.cube` LUT 工具链（均基于四面体插值）：

1. **供 Sony S-Log3 / S-Gamut3(.Cine) 使用的富士 LUT**（[`fuji_to_sony_lut.py`](fuji_to_sony_lut.py)）将富士 F-Log2 LUT 的输入改为 Sony Log，输出沿用原表的显示或技术编码。
2. **Camera Raw Style LUT**（[`lut_to_acr.py`](lut_to_acr.py) 及批量构建器）生成 64³ 创意 LUT。彩色风格在假定的 SDR 接口中匹配输入和输出格点的相对线性 CIE Y，ACROS 沿用原表的黑白灰度映射。

## 安装依赖

```bash
uv sync
# 或: pip install -r requirements.txt
```

---

## 一、F-Log2 → S-Log3 / S-Gamut3(.Cine)（视频工作流）

链路为 `S-Log3 解码 → 线性 S-Gamut3(.Cine) 转 F-Gamut → 在源 LUT 的线性输入域内压缩色度 → F-Log2 编码 → 四面体采样源表`。

域边界映射保留 F-Log2 线性段容纳的负值，接近边界时沿等 Y 方向逐渐收向中性。输入 Y 超出可表示的中性范围时以最近的中性边界为锚点。S-Log3 输入按 Sony 公式使用 10 位码值除以 1023。应用时应与宿主的信号范围、素材色域和源 LUT 的输出编码匹配。[Sony 技术说明](https://pro.sony/s3/cms-static-content/uploadfile/06/1237494271406.pdf) · [Fujifilm F-Log2 数据表](https://dl.fujifilm-x.com/support/lut/F-Log2_DataSheet_E_Ver.1.1.pdf)

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
| `--output-grid-size` | `auto` | 保留源分辨率（33/65）或指定 `17` / `33` / `65` / `129` |

机内监看按相机说明选择网格。例如 Sony FX30 支持 17³ 或 33³，导入后应选择与构建时一致的 S-Gamut3.Cine 或 S-Gamut3。[Sony FX30 导入手册](https://helpguide.sony.net/ilc/2220/v1/en/contents/TP1000888940.html)

---

## 二、Adobe Camera Raw Style LUT（RAW 摄影工作流）

彩色链路为 `假定的 sRGB 输入 → 解码并映射到相机 Log → 四面体采样源表 → 按源显示曲线解码 → 匹配相对线性 CIE Y 并以固定 OKLab 色相收缩越界色度 → 编码回 sRGB 64³`。

相机 Log 的输入由已显影的 SDR RGB 近似得到。曝光偏移和高光展开会改变源 LUT 的取样位置。保亮度约束适用于生成时的线性 Y 和采样格点，实际像素还受宿主色域、传递函数、插值和处理顺序影响。RAW 场景曝光、HDR 动态范围和感知明度属于不同的量。

- 富士彩色 LUT 按 GFX ETERNA 55 白皮书的监看基准使用 Gamma 2.2，ACROS 同时保留源 LUT 的通道混合与影调。[富士白皮书，第 13 页](https://dl.fujifilm-x.com/support/lut/GFX_ETERNA_WhitePaper_260206_v101.pdf#page=13)
- ARRI DRT 和 Sony VENICE 构建器使用 Gamma 2.4。Sony26 的 Quirky 根据文件头使用 Gamma 2.4，并保留原项目选定的创意曝光偏移 +0.5 EV。Sony26 其余表暂按 sRGB 解码，有源表规格时可覆盖该假设。
- CrystalFilm 和 AnalogFilm 是 OKLab 创意配方。分离色调集中于低彩度区域，接近中性时色相角对小幅颜色变化敏感。输出 LUT 经分段插值。

```bash
# 已知源输出为 Rec.709 Gamma 2.4 的 S-Log3 LUT → ACR Style LUT
.venv/bin/python lut_to_acr.py --space srgb --tone preserve --display-gamma 2.4 --size 64 \
    input.cube "output/acr_style/My Look Style.cube"

# 批量构建富士官方 F-Log2 胶片模拟（自动跳过 FLog2-709 / WDR 技术曲线）
.venv/bin/python build_fuji_style.py

# 批量构建 ARRI 官方 LogC3/LogC4（REVEAL、Alexa Classic、ALF2 与 Look Library）
# 官方下载：https://www.arri.com/en/learn/camera-systems/technical-downloads
.venv/bin/python build_arri_style.py

# 批量构建 Sony VENICE 官方 Look（s709 / Look 7525 / Look 1）
# 官方下载：https://sony-cinematography.com/resources/luts/
.venv/bin/python build_film_style.py

# 批量构建精选索尼 S-Log3 风格包（Quirky_33x 使用 Gamma 2.4 与 +0.5 EV）
.venv/bin/python build_sony26_style.py

# 生成两支原创 OKLab 风格 LUT（CrystalFilm 和 AnalogFilm）
.venv/bin/python build_ultimate_style.py

# 一键全量重建并部署到 Camera Raw（支持 WSL/macOS 自动定位或手动传参）
./rebuild_all.sh
./redeploy_to_acr.sh
```

`lut_to_acr.py` 常用参数：

| 参数 | 默认值 | 说明 |
|---|---|---|
| `--tone` | `lut` | `preserve`（匹配格点上的相对线性 Y） / `lut`（保留源 LUT 影调） |
| `--space` | `srgb` | 假定的目标接口。`prophoto` 使用标准 ROMM 传递函数，`prophoto-gamma` 使用 ProPhoto 基色与 sRGB 曲线 |
| `--output-mode` | `as-is` | 源输出已与目标编码一致时使用 `as-is`，其余可用 `display-709` 转换源输出到目标 |
| `--display-gamma` | `srgb` / `2.4` | 源输出的解码曲线，和 `--space` 独立。通用 CLI 的 `preserve` 默认 sRGB，`display-709` 默认纯 Gamma 2.4 |
| `--ev-offset` | `0.0` | 输入 S-Log3 查表前的曝光偏移 EV（如校准 ETTR LUT） |
| `--size` | `64` | 输出格点数（2–64，Camera Raw 上限为 64） |
| `--interp` | `tetrahedral` | 插值方式（`tetrahedral` / `trilinear`） |
| `--report` | 关闭 | 输出矩阵、灰阶探针及两种插值在格点间的相对 Y 误差统计 |

在 Camera Raw 的 Color Grading → Apply LUT → Choose a file 可导入 `.cube`，网格上限为 64³。批量部署旨在用于专门存放本项目 LUT 的目录。[Adobe Apply LUT 文档](https://helpx.adobe.com/camera-raw/desktop/edit-and-enhance-images/tone-and-color/apply-luts-to-photos-in-camera-raw.html)

### 测量 Adobe 宿主的 LUT 接口

Adobe 的导入文档未给出 Apply LUT 的求值色域、传递函数或插值。可以在目标版本中用诊断色卡和一个交叉通道 LUT 比较候选接口。

```bash
uv sync --extra probe
.venv/bin/python probe_acr.py generate output/acr_probe
.venv/bin/python probe_acr.py score baseline.tif graded.tif
```

在 Camera Raw 中打开生成的 `ACR Probe Chart.tif`，关闭自动调整、裁切和 HDR，导出同尺寸 8 位 sRGB TIFF 作为 `baseline.tif`。然后以 Amount 100 应用 `ACR Cross Channel Probe.cube`，用同样的设置导出 `graded.tif`。评分以 8 位码值显示各色域、曲线和插值组合的平均及最大误差。应同时记录宿主版本。候选误差都偏大时，可进一步检查导出设置或宿主处理顺序。

Windows Camera Raw 19.0（Process Version 15.4）的 SDR 实测支持默认的 sRGB 编码值接口和四面体插值。对 48 个色块应用 2³ 探针后，预测与导出的平均绝对误差为 0.26 个 8 位码值，最大为 0.55。第二接近的候选是 Adobe RGB 加四面体插值，平均误差为 7.33 个码值。该结果适用于这次测试的 Camera Raw 版本、SDR TIFF 路径及探针设置。

---

## 测试与目录结构

```bash
.venv/bin/python -m unittest discover -s tests -v
```

```text
lut_convert/
├── fuji_to_sony_lut.py     # ① F-Log2 → S-Log3 / S-Gamut3(.Cine)（视频）
├── lut_to_acr.py           # ② S-Log3 → Adobe Camera Raw Style（核心转换）
├── probe_acr.py            # ② 生成色卡与诊断 LUT，比较宿主接口候选
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
