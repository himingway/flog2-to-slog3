# F-Log2 转 S-Log3 LUT 转换器

将富士官方 F-Log2 胶片模拟 3D LUT 转换为适用于索尼 S-Log3 素材的专业工具。

[English Version](README.md)

## ✨ 功能特点

- 🎨 **数学级精确** - 纯函数复合转换，无经验性的曝光、黑阶或 RGB 增益修正
- 🔄 **坐标重映射** - 直接在 LUT 网格层面完成转换，无级联精度损失
- 🎯 **网格中心拟合** - 在不升级网格尺寸的前提下最小化固定网格插值误差
- ⚡ **高性能** - 矩阵运算预计算一次，批量处理速度快
- 📦 **网格保留** - 自动识别 33/65 网格 LUT，保持原始分辨率

## 🔬 数学模型

转换采用严格的函数复合流程：

1. **解码** 输入的 S-Log3 码值，回到场景线性光空间
2. **色域映射** 在线性域中完成 S-Gamut3(.Cine) → F-Gamut 转换
3. **重新编码** 为 F-Log2 坐标
4. **采样** 原始富士 LUT 在这些坐标上的值，生成新的索尼 LUT

这意味着转换后的 LUT 在连续函数层面严格对应于原始富士 LUT。剩余误差仅来自非线性输入变换的有限 3D 网格重采样。

## 🚀 快速开始

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

调整拟合迭代次数：

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --fit-iterations 2
```

## 📊 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `-i, --input` | 必填 | 富士 LUT 根目录 |
| `--input-colourspace` | `S-Gamut3.Cine` | 索尼输入色域：`S-Gamut3.Cine` 或 `S-Gamut3` |
| `--output-grid-size` | `auto` | 输出 LUT 网格大小：`auto`（保持源文件）、`33`、`65`、`129` |
| `--fit-iterations` | `2` | 网格中心拟合迭代次数：`0`、`1`、`2`、`3`。降低固定网格插值误差 |

## 📁 输入与输出

脚本会扫描 `.cube` 文件，仅处理名称匹配 `FLog2_to_*` 的 LUT。`F-Log`、`F-Log2C` 等其他类型会被自动跳过。

输出目录规则：

```text
Sony_SLog3_Converted_<输入目录名>/
```

文件名会将 `FLog2` 替换为 `SLog3`，路径中的 `33Grid` / `65Grid` 会更新为实际输出网格。

## 📋 索尼素材要求

转换后的 LUT 正确使用的前提：

- 素材必须是真实的 `S-Log3`
- 色域设置必须与拍摄时一致

如果你的素材是 `S-Gamut3` 而不是 `S-Gamut3.Cine`，请显式指定：

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --input-colourspace S-Gamut3
```

## 🧪 质量策略

- **默认网格**：`auto` 保持原始 33/65 分辨率
- **默认拟合**：`2` 次网格中心拟合迭代，在不升级到 129 网格的前提下最小化插值误差
- **最高质量**：手动升级到 129 网格，以更大文件体积换取理论最低误差
