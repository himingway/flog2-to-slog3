# F-Log2 to S-Log3 LUT Converter

Convert Fujifilm official F-Log2 film simulation 3D LUTs to work natively with Sony S-Log3 footage.

[中文版本](README.zh-CN.md)

## Features

- **Mathematical Precision** - Pure function composition, no empirical exposure, black level, or RGB gain corrections
- **Tetrahedral Interpolation** - Industry-standard algorithm with true affine invariance
- **No Dark Clamping** - Preserves legitimate negative values from gamut conversion, preventing hue shifts in shadows
- **High Performance** - Matrix operations precomputed once, fast batch processing
- **Grid Preservation** - Auto-detects 33/65 grid LUTs and maintains original resolution
- **DaVinci Resolve Ready** - Writes standard Iridas `.cube` files readable by Resolve

## Mathematical Model

The converted LUT is defined by strict function composition:

```
LUT_SLog3(x) = LUT_FLog2( φ(x) )
φ(x) = FLog2_encode( M_Bradford · SLog3_decode(x) )
```

### Pipeline

1. **S-Log3 Decode** — Sony's piecewise log-to-linear function recovers scene-linear light from code values
2. **Gamut Mapping** — Linear 3×3 matrix with Bradford chromatic adaptation: S-Gamut3(.Cine) → F-Gamut
3. **F-Log2 Encode** — Fuji's piecewise linear-to-log function maps to F-Log2 code value space (negative linear values preserved, not clamped)
4. **Tetrahedral Interpolation** — Sample the original Fujifilm LUT at the mapped coordinates

This means the converted LUT corresponds strictly to the original Fujifilm LUT at the continuous function level.

### Tetrahedral Interpolation

Each voxel is subdivided into 6 tetrahedra. Within each tetrahedron, interpolation uses 4 vertices with barycentric coordinates:

```
f(x,y,z) = a + b·x + c·y + d·z    (affine, no cross terms)
```

The gamut mapping step is an affine function G(x) = Mx + b. For any affine function, tetrahedral interpolation is an **exact** reconstruction: the 4-point affine interpolation is uniquely determined by its values at the 4 vertices, so the interpolation matches the underlying function perfectly. The gamut mapping introduces **zero** additional interpolation error regardless of grid resolution.

Other properties:
- ∂³f/∂x∂y∂z = 0 within each tetrahedron — no spurious cross-channel contamination
- Each sample is influenced by only 4 vertices (not 8), preserving color transition sharpness

### Negative Value Preservation

Gamut conversion can produce negative linear values for out-of-gamut colors. F-Log2's encoding has a valid linear extension segment below zero that handles these naturally. Clamping to zero would introduce a gradient discontinuity, causing hue shifts in shadow regions.

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

The generated files use the standard `TITLE` and `LUT_3D_SIZE` headers and can be
copied directly into DaVinci Resolve's LUT folder, followed by a LUT refresh.
The selected Sony input gamut is recorded in the file comments.

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
- **Tetrahedral interpolation**: industry-standard algorithm with proven accuracy
- **For maximum quality**: Upgrade to 65 or 129 grid for finer sampling

When one output grid is explicitly selected for a directory containing multiple
source resolutions, converted files from a different source grid are placed in a
`from33Grid` or `from65Grid` subdirectory so no LUT is overwritten.
