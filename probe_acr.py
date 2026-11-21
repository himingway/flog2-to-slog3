"""Generate and score a color-space and interpolation probe for Adobe Apply LUT."""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

import lut_to_acr as m


PATCH_SIZE = 32
ROWS = 6
COLS = 8
SPACES = ("srgb", "srgb-linear", "adobergb", "adobergb-linear",
          "prophoto", "prophoto-gamma", "prophoto-linear")


def probe_table():
    r, g, b = m.uniform_grid(2).T
    return np.stack((0.15 + 0.55 * r * g, 0.12 + 0.60 * g * b,
                     0.10 + 0.65 * b * r), axis=-1).reshape(2, 2, 2, 3)


def generate(directory):
    directory.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1103)
    patches = rng.integers(12, 244, size=(ROWS, COLS, 3), dtype=np.uint8)
    patches[0] = np.array([12, 32, 64, 100, 128, 166, 205, 243])[:, None]
    pixels = np.repeat(np.repeat(patches, PATCH_SIZE, axis=0), PATCH_SIZE, axis=1)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    Image.fromarray(pixels).save(directory / "ACR Probe Chart.tif", icc_profile=profile)
    m.write_cube(directory / "ACR Cross Channel Probe.cube", probe_table(),
                 "ACR Cross Channel Probe", note="Diagnostic LUT for host color space and interpolation")


def read_patches(path):
    with Image.open(path) as image:
        expected = (COLS * PATCH_SIZE, ROWS * PATCH_SIZE)
        if image.size != expected:
            raise ValueError(f"{path}: expected {expected[0]}×{expected[1]} without resizing or cropping")
        pixels = np.asarray(image.convert("RGB"), dtype=np.float64) / 255.0
    patches = pixels.reshape(ROWS, PATCH_SIZE, COLS, PATCH_SIZE, 3)
    inset = slice(PATCH_SIZE // 4, 3 * PATCH_SIZE // 4)
    return np.median(patches[:, inset, :, inset, :], axis=(1, 3)).reshape(-1, 3)


def score(baseline, graded):
    table = probe_table()
    lin_srgb = m.decode_space(baseline, "srgb")
    results = []
    for space in SPACES:
        _, from_srgb = m.conversion_matrices(space)
        to_srgb = np.linalg.inv(from_srgb)
        codes = m.encode_space(lin_srgb @ from_srgb.T, space)
        for name, sample in (("tetrahedral", m.sample_table_tetra), ("trilinear", m.sample_table)):
            looked = m.decode_space(sample(table, codes), space)
            predicted = m.encode_space(looked @ to_srgb.T, "srgb")
            error = np.abs(predicted - graded)
            results.append((float(error.mean()), float(error.max()), space, name))
    return sorted(results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("generate")
    create.add_argument("directory", type=Path)
    compare = commands.add_parser("score")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("graded", type=Path)
    args = parser.parse_args()
    if args.command == "generate":
        generate(args.directory)
        return
    for mean, maximum, space, sampler in score(read_patches(args.baseline), read_patches(args.graded)):
        print(f"{space:16s} {sampler:12s} mean {mean * 255:6.2f} / 255   max {maximum * 255:6.2f} / 255")


if __name__ == "__main__":
    main()
