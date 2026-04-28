## LUT Convert

将 Fuji 官方 `F-Log2 -> Look` 3D LUT 批量转换为 Sony `S-Log3 -> Look` 3D LUT，目标是让 Sony 拍摄的 S-Log3 素材可以直接套用转换后的 LUT。

### 数学模型

当前转换流程采用严格的函数复合，不再混入经验性的曝光、黑阶或 RGB 增益修正：

1. 对输入的 `S-Log3` 码值做解码，回到场景线性光。
2. 在线性域中完成 `S-Gamut3(.Cine) -> F-Gamut` 的色域映射。
3. 将结果重新编码为 `F-Log2`。
4. 用得到的 `F-Log2` 坐标采样原始 Fuji LUT，生成新的 Sony LUT。

这意味着转换后的 LUT 在连续函数层面严格对应于原始 Fuji LUT。剩余误差只来自有限 3D 网格对非线性输入变换的重采样。

### 默认策略

- 默认输入色域为 `S-Gamut3.Cine`。
- 默认输出网格为 `auto`：
	- `33` 源 LUT 保持 `33` 网格
	- `65` 源 LUT 保持 `65` 网格
- 默认启用 `2` 次 cell-center 拟合，在不升到 `129` 网格的前提下进一步压低固定网格的插值误差。
- 如果你愿意用更大的输出体积换更低误差，可以手动把 `33` 源 LUT 升到 `65`，或把输出直接指定到 `129`。

### 安装

项目依赖定义在 `pyproject.toml` 中，当前主要依赖：

- `colour-science`
- `numpy`
- `scipy`

如果你使用当前仓库自带虚拟环境，直接运行：

```bash
source .venv/bin/activate
```

### 用法

基础命令：

```bash
python fuji_to_sony_lut.py -i ./gfx-eterna-55-3d-lut-v100
```

显式指定 Sony 输入色域：

```bash
python fuji_to_sony_lut.py \
	-i ./gfx-eterna-55-3d-lut-v100 \
	--input-colourspace S-Gamut3.Cine
```

显式指定输出网格：

```bash
python fuji_to_sony_lut.py \
	-i ./gfx-eterna-55-3d-lut-v100 \
	--output-grid-size 65
```

调整固定网格下的拟合强度：

```bash
python fuji_to_sony_lut.py \
	-i ./gfx-eterna-55-3d-lut-v100 \
	--fit-iterations 2
```

### CLI 参数

- `-i`, `--input`: Fuji LUT 根目录。
- `--input-colourspace`: Sony 输入色域，可选 `S-Gamut3.Cine` 或 `S-Gamut3`。
- `--output-grid-size`: 输出 LUT 网格大小，可选 `33`、`65`、`129`，默认 `auto`，会保留源 LUT 的 `33/65` 网格；也可以手动升到更高网格。
- `--fit-iterations`: 固定网格下的 cell-center 拟合迭代次数，可选 `0`、`1`、`2`、`3`，默认 `2`。

### 输入与输出

脚本会扫描输入目录下的 `.cube` 文件，并只处理名称匹配 `FLog2_to_*` 的 LUT；`F-Log`、`F-Log2C` 等其他类型会被跳过。

输出目录规则：

```text
Sony_SLog3_Converted_<输入目录名>/
```

文件名会将 `FLog2` 替换为 `SLog3`，并将路径中的 `33Grid` / `65Grid` 更新为实际输出网格。

### 对 Sony 实拍素材的要求

要让转换后的 LUT 直接可用，前提是：

- 素材确实是 `S-Log3`
- 输入色域设置与拍摄时一致

如果素材是 `S-Gamut3` 而不是 `S-Gamut3.Cine`，需要显式传入：

```bash
python fuji_to_sony_lut.py \
	-i ./gfx-eterna-55-3d-lut-v100 \
	--input-colourspace S-Gamut3
```

### 当前仓库状态

转换结果目录属于生成产物，已建议通过 `.gitignore` 忽略。
