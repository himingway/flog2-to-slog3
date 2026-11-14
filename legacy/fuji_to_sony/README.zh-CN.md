# F-Log2 转 S-Log3 LUT 转换器

将富士官方 F-Log2 胶片模拟 3D LUT 转换为适用于索尼 S-Log3 素材的专业工具。

[English Version](README.md)

## 功能特点

- **数学级精确** - 纯函数复合转换，无经验性的曝光、黑阶或 RGB 增益修正
- **四面体插值** - 影视后期工业标准算法，具备真正的仿射不变性
- **无暗部截断** - 保留色域转换产生的合法负值，防止暗部色相偏转
- **高性能** - 矩阵运算预计算一次，批量处理速度快
- **网格保留** - 自动识别 33/65 网格 LUT，保持原始分辨率
- **DaVinci Resolve 直接可用** - 输出标准 Iridas `.cube` 文件，可直接导入 Resolve

## 数学模型

转换后的 LUT 由严格的函数复合定义：

```
LUT_SLog3(x) = LUT_FLog2( φ(x) )
φ(x) = FLog2_encode( M_Bradford · SLog3_decode(x) )
```

### 转换流程

1. **S-Log3 解码** — 索尼的分段对数→线性函数，从码值恢复场景线性光
2. **色域映射** — Bradford 色度适应的线性 3×3 矩阵变换：S-Gamut3(.Cine) → F-Gamut
3. **F-Log2 编码** — 富士的分段线性→对数函数，映射到 F-Log2 码值空间（保留负值，不截断）
4. **四面体插值** — 在映射后的坐标上采样原始富士 LUT

这意味着转换后的 LUT 在连续函数层面严格对应于原始富士 LUT。

### 四面体插值

每个体素被细分为 6 个四面体。在每个四面体内，插值使用 4 个顶点进行重心坐标加权：

```
f(x,y,z) = a + b·x + c·y + d·z    （仿射函数，无交叉项）
```

色域映射步骤是仿射函数 G(x) = Mx + b。对于任何仿射函数，四面体插值是**精确重建**：4 点仿射插值由 4 个顶点处的函数值唯一确定，因此插值与底层函数完全一致。色域映射引入**零**额外插值误差，与网格精度无关。

其他性质：
- 四面体内 ∂³f/∂x∂y∂z = 0——不存在虚假的跨通道污染
- 每个采样点仅受 4 个顶点影响（而非 8 个），保持色彩过渡的锐度

### 负值保留

色域转换可能对色域外的颜色产生负的线性值。F-Log2 编码在零以下有合法的线性延拓段，可以自然处理这些值。如果截断为零，将引入梯度不连续性，导致暗部区域色相偏转。

## 快速开始

### 安装依赖

```bash
uv sync
```

### 使用方法

基础转换：

```bash
uv run python fuji_to_sony_lut.py -i ./gfx-eterna-55-3d-lut-v100
```

指定索尼输入色域：

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --input-colourspace S-Gamut3.Cine
```

指定输出网格大小：

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --output-grid-size 65
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-i, --input` | 必填 | 富士 LUT 根目录 |
| `--input-colourspace` | `S-Gamut3.Cine` | 索尼输入色域：`S-Gamut3.Cine` 或 `S-Gamut3` |
| `--output-grid-size` | `auto` | 输出 LUT 网格大小：`auto`（保持源文件）、`33`、`65`、`129` |

## 输入与输出

脚本会扫描 `.cube` 文件，仅处理名称匹配 `FLog2_to_*` 的 LUT。`F-Log`、`F-Log2C` 等其他类型会被自动跳过。

生成文件使用标准 `TITLE` 和 `LUT_3D_SIZE` 头部，可直接复制到 DaVinci Resolve
的 LUT 目录并刷新 LUT。所选的 Sony 输入色域会写入文件注释中。

输出目录规则：

```text
Sony_SLog3_Converted_<输入目录名>/
```

文件名会将 `FLog2` 替换为 `SLog3`，路径中的 `33Grid` / `65Grid` 会更新为实际输出网格。

## 索尼素材要求

转换后的 LUT 正确使用的前提：

- 素材必须是真实的 `S-Log3`
- 色域设置必须与拍摄时一致

如果你的素材是 `S-Gamut3` 而不是 `S-Gamut3.Cine`，请显式指定：

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --input-colourspace S-Gamut3
```

## 质量策略

- **默认网格**：`auto` 保持原始 33/65 分辨率
- **四面体插值**：工业标准算法，经过充分验证的精度
- **最高质量**：手动升级到 65 或 129 网格，以更精细的采样换取更高精度

当目录中同时包含不同源网格、并显式指定一个输出网格时，来自其他源网格的文件会放入
`from33Grid` 或 `from65Grid` 子目录，避免同名 LUT 相互覆盖。
