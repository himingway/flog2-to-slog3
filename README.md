# F-Log2 to S-Log3 LUT Converter

Convert Fujifilm official F-Log2 film simulation 3D LUTs to work natively with Sony S-Log3 footage.

[中文版本](README.zh-CN.md)

## ✨ Features

- 🎨 **Mathematical Precision** - Pure function composition, no empirical exposure, black level, or RGB gain corrections
- 🔄 **Coordinate Remapping** - Direct transformation at LUT grid level, no cascading precision loss
- 🎯 **Cell-Center Fitting** - Minimize fixed-grid interpolation errors without upgrading grid size
- ⚡ **High Performance** - Matrix operations precomputed once, fast batch processing
- 📦 **Grid Preservation** - Auto-detects 33/65 grid LUTs and maintains original resolution

## 🔬 Mathematical Model

The conversion uses rigorous function composition:

1. **Decode** input S-Log3 code values to scene-linear light
2. **Gamut Mapping** from S-Gamut3(.Cine) to F-Gamut in linear domain
3. **Re-encode** to F-Log2 coordinates
4. **Sample** the original Fujifilm LUT at these coordinates to generate the new Sony LUT

This means the converted LUT corresponds strictly to the original Fujifilm LUT at the continuous function level. Residual error comes only from the finite 3D grid resampling of the nonlinear input transform.

## 🚀 Quick Start

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

Adjust fitting iterations:

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --fit-iterations 2
```

## 📊 Parameter Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `-i, --input` | required | Root directory of Fujifilm LUTs |
| `--input-colourspace` | `S-Gamut3.Cine` | Sony input colorspace: `S-Gamut3.Cine` or `S-Gamut3` |
| `--output-grid-size` | `auto` | Output LUT grid size: `auto` (preserve source), `33`, `65`, `129` |
| `--fit-iterations` | `2` | Cell-center fitting iterations: `0`, `1`, `2`, `3`. Reduces fixed-grid interpolation error |

## 📁 Input & Output

The script scans for `.cube` files and only processes LUTs matching `FLog2_to_*`. Other types like `F-Log` and `F-Log2C` are skipped.

Output directory convention:

```text
Sony_SLog3_Converted_<input_directory_name>/
```

Filenames replace `FLog2` with `SLog3`, and path components `33Grid` / `65Grid` are updated to match the actual output grid.

## 📋 Requirements for Sony Footage

For the converted LUTs to work correctly:

- Footage must be actual `S-Log3`
- Colorspace setting must match what was used during shooting

If your footage is `S-Gamut3` instead of `S-Gamut3.Cine`, specify it explicitly:

```bash
uv run python fuji_to_sony_lut.py \
    -i ./gfx-eterna-55-3d-lut-v100 \
    --input-colourspace S-Gamut3
```

## 🧪 Quality Strategy

- **Default grid**: `auto` preserves original 33/65 resolution
- **Default fitting**: `2` iterations of cell-center fitting to minimize interpolation errors without upgrading to 129 grid
- **For maximum quality**: Upgrade to 129 grid manually for lowest possible error at the cost of larger file size
