# F-Log2 to S-Log3 LUT Converter

Convert Fujifilm official F-Log2 film simulation 3D LUTs to work natively with Sony S-Log3 footage.

[中文版本](README.zh-CN.md)

## Features

- **Mathematical Precision** - Pure function composition, no empirical exposure, black level, or RGB gain corrections
- **Tetrahedral Interpolation** - Industry-standard algorithm that eliminates cross-coupling artifacts of trilinear interpolation
- **No Dark Clamping** - Preserves legitimate negative values from gamut conversion, preventing hue shifts in shadows
- **High Performance** - Matrix operations precomputed once, fast batch processing
- **Grid Preservation** - Auto-detects 33/65 grid LUTs and maintains original resolution

## Mathematical Model

The conversion uses rigorous function composition:

1. **Decode** input S-Log3 code values to scene-linear light
2. **Gamut Mapping** from S-Gamut3(.Cine) to F-Gamut in linear domain
3. **Re-encode** to F-Log2 coordinates
4. **Sample** the original Fujifilm LUT at these coordinates using tetrahedral interpolation

This means the converted LUT corresponds strictly to the original Fujifilm LUT at the continuous function level.

## Why Tetrahedral Interpolation

### The Problem with Trilinear Interpolation

Trilinear interpolation factors into three sequential 1D linear interpolations:

```
f(x,y,z) = Σ (8 corner weights) × f_corner
```

The weight product `x·y·z` introduces a cubic **cross-coupling term** (∂³f/∂x∂y∂z ≠ 0) that has no physical basis in color transforms. For the gamut mapping step — which is a **linear 3×3 matrix** — trilinear interpolation is an approximation, not an exact reconstruction.

### Why Tetrahedral is Better

Each voxel is subdivided into 6 tetrahedra. Within each tetrahedron, interpolation uses 4 vertices with barycentric coordinates:

```
f(x,y,z) = a + b·x + c·y + d·z    (true linear, no cross terms)
```

**Key mathematical properties:**

1. **Affine invariance**: For the linear gamut transform (M·x + b), tetrahedral interpolation is **exact** — it reproduces affine functions perfectly, while trilinear introduces cross-term errors
2. **No artificial coupling**: ∂³f/∂x∂y∂z = 0 within each tetrahedron — the mixed partial derivative that plagues trilinear interpolation is eliminated
3. **Better locality**: Each sample point is influenced by only 4 vertices (not 8), reducing over-smoothing of color transitions

### Quantitative Proof

Benchmarked against 129³ ground truth on `FLog2_to_ETERNA_33grid`:

| Metric | Trilinear + Cell-Center Fitting | Tetrahedral (New) | Improvement |
|--------|-------------------------------|-------------------|-------------|
| **RMSE** | 0.02852 (29.18 / 10-bit) | 0.00912 (9.33 / 10-bit) | **68.0%** |
| **Mean Abs Error** | 0.01232 | 0.00154 | **87.5%** |
| **95th Percentile** | 0.07057 | 0.00475 | **93.3%** |
| **99th Percentile** | 0.11552 | 0.02671 | **76.9%** |
| **Shadow RMSE** (<0.1) | 0.03057 (31.27 / 10-bit) | 0.00679 (6.95 / 10-bit) | **77.8%** |

The improvement comes from two independent factors:

- **Removing the 1e-8 clamp** on linear values: preserves legitimate negative values from gamut conversion, dramatically improving shadow accuracy (+77.8% in dark regions)
- **Tetrahedral interpolation**: eliminates cross-coupling artifacts, reducing RMSE by ~17.6% even when both methods use unclamped coordinates

Run the benchmark yourself: `uv run python benchmark_interpolation.py`

## Quick Start

### Install Dependencies

```bash
uv sync
```

### Usage

Basic conversion:

```bash
uv run python fuji_to_sony_lut.py -i ./gfx-eterna-55-3d-lut-v100
```

Specify Sony input colorspace:

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --input-colourspace S-Gamut3.Cine
```

Specify output grid size:

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --output-grid-size 65
```

## Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `-i, --input` | required | Root directory of Fujifilm LUTs |
| `--input-colourspace` | `S-Gamut3.Cine` | Sony input colorspace: `S-Gamut3.Cine` or `S-Gamut3` |
| `--output-grid-size` | `auto` | Output LUT grid size: `auto` (preserve source), `33`, `65`, `129` |

## Input & Output

The script scans for `.cube` files and only processes LUTs matching `FLog2_to_*`. Other types like `F-Log` and `F-Log2C` are skipped.

Output directory convention:

```text
Sony_SLog3_Converted_<input_directory_name>/
```

Filenames replace `FLog2` with `SLog3`, and path components `33Grid` / `65Grid` are updated to match the actual output grid.

## Requirements for Sony Footage

For the converted LUTs to work correctly:

- Footage must be actual `S-Log3`
- Colorspace setting must match what was used during shooting

If your footage is `S-Gamut3` instead of `S-Gamut3.Cine`, specify it explicitly:

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --input-colourspace S-Gamut3
```

## Quality Strategy

- **Default grid**: `auto` preserves original 33/65 resolution
- **Tetrahedral interpolation**: industry-standard algorithm with proven 68% RMSE improvement over trilinear+fitting
- **For maximum quality**: Upgrade to 65 or 129 grid for finer sampling
