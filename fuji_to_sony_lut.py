import argparse
import logging
import time
from pathlib import Path
from typing import Dict

import numpy as np
import colour
from colour.algebra import table_interpolation_tetrahedral

# ---------------------------------------------------------
# 1. 日志系统配置 (工业级日志监控)
# ---------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("LUT_Converter")

# ---------------------------------------------------------
# 2. 核心数学计算引擎
# ---------------------------------------------------------
def map_slog3_samples_to_flog2(
    slog3_rgb: np.ndarray,
    input_colourspace: str,
    domain: np.ndarray,
) -> np.ndarray:
    """
    将 S-Log3 / S-Gamut3(.Cine) 采样点映射到 F-Log2 / F-Gamut 坐标。
    """
    # 1. 解码到线性光
    linear_slog3 = colour.models.log_decoding(slog3_rgb, 'S-Log3')

    # 2. 色域转换 (矩阵运算)
    cs_slog3 = colour.RGB_COLOURSPACES[input_colourspace]
    cs_flog2 = colour.RGB_COLOURSPACES['F-Gamut']
    linear_flog2 = colour.RGB_to_RGB(
        linear_slog3, cs_slog3, cs_flog2, chromatic_adaptation_transform='Bradford'
    )

    # 不截断负值：F-Log2 编码底层在暗部有合法的线性延拓段，
    # 可以妥善处理色域转换中出现的微小负值。强行截断会导致色相严重偏转。
    flog2_coords = colour.models.log_encoding(linear_flog2, 'F-Log2')

    # 获取原始 LUT 域范围
    domain_min = np.asarray(domain[0], dtype=float)
    domain_max = np.asarray(domain[1], dtype=float)

    # 仅在最终坐标级进行限制，防止超出 3D 网格索引范围
    return np.clip(flog2_coords, domain_min, domain_max)


def precompute_color_mapping(
    size: int,
    input_colourspace: str,
    domain: np.ndarray,
) -> np.ndarray:
    """
    预计算 S-Log3 到 F-Log2 的精确 3D 坐标映射。
    """
    logger.info(
        f"正在计算色彩科学映射 (网格精度: {size}x{size}x{size}, 输入色域: {input_colourspace})..."
    )

    samples = np.linspace(0, 1, size)
    grid = np.meshgrid(samples, samples, samples, indexing='ij')
    slog3_rgb = np.stack(grid, axis=-1).reshape(-1, 3)

    return map_slog3_samples_to_flog2(slog3_rgb, input_colourspace, domain)


def resolve_output_grid_size(source_grid_size: int, requested_grid_size: int | None) -> int:
    """解析输出 LUT 网格精度"""
    if requested_grid_size is not None:
        return requested_grid_size
    return min(source_grid_size, 65)


def rewrite_grid_marker(path: Path, grid_size: int) -> Path:
    """将路径中的网格标识同步到实际输出网格精度"""
    rewritten_parts = [f"{grid_size}Grid" if part.endswith("Grid") else part for part in path.parts]
    return Path(*rewritten_parts)

# ---------------------------------------------------------
# 3. 业务处理主流程
# ---------------------------------------------------------
def process_lut_directory(input_dir: str,
                          input_colourspace: str = 'S-Gamut3.Cine',
                          output_grid_size: int | None = None):
    """
    遍历目录并执行 LUT 转换的主函数。
    """
    root_dir = Path(input_dir).resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        logger.error(f"输入路径无效或不存在: {root_dir}")
        return

    output_root = root_dir.parent / f"Sony_SLog3_Converted_{root_dir.name}"
    output_root.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info(f"启动 LUT 批处理引擎")
    grid_mode = output_grid_size if output_grid_size is not None else 'auto'
    logger.info(
        f"参数: Sony 色域 {input_colourspace} | 算法: 四面体插值 (Tetrahedral) | 输出网格 {grid_mode}"
    )
    logger.info("=" * 60)

    start_time = time.time()
    mapping_cache: Dict[tuple[int, tuple[float, ...]], np.ndarray] = {}

    all_cubes = list(root_dir.rglob("*.cube"))
    stats = {"success": 0, "skipped": 0, "failed": 0}

    for cube_path in all_cubes:
        rel_path = cube_path.relative_to(root_dir)
        cube_name_posix = cube_path.as_posix()
        cube_name = cube_path.name

        # 过滤机制：只处理 F-Log2
        if "F-Log/" in cube_name_posix or "FLog_to" in cube_name:
            stats["skipped"] += 1
            continue
        if "F-Log2C" in cube_name_posix or "FLog2C_to" in cube_name:
            stats["skipped"] += 1
            continue
        if "FLog2_to" not in cube_name:
            stats["skipped"] += 1
            continue

        try:
            # 1. 加载原始 LUT
            orig_lut = colour.read_LUT(str(cube_path))
            source_grid_size = orig_lut.size
            grid_size = resolve_output_grid_size(source_grid_size, output_grid_size)
            domain = np.asarray(orig_lut.domain, dtype=float)
            cache_key = (grid_size, tuple(domain.reshape(-1)))

            # 构建输出路径
            output_rel_path = rewrite_grid_marker(rel_path, grid_size)
            out_file_path = output_root / output_rel_path
            out_file_path.parent.mkdir(parents=True, exist_ok=True)
            new_name = cube_name.replace("FLog2", "SLog3").replace(f"_{source_grid_size}grid_", f"_{grid_size}grid_")
            final_out_path = out_file_path.with_name(new_name)

            # 2. 从缓存中获取映射坐标
            if cache_key not in mapping_cache:
                mapping_cache[cache_key] = precompute_color_mapping(
                    grid_size,
                    input_colourspace,
                    domain,
                )
            coords = mapping_cache[cache_key]

            # 使用工业级四面体插值 (Tetrahedral)
            new_table = orig_lut.apply(coords, interpolator=table_interpolation_tetrahedral)

            # 3. 封装新的 3D LUT
            new_lut = colour.LUT3D(
                table=new_table.reshape((grid_size, grid_size, grid_size, 3)),
                name=f"Sony_{new_name.replace('.cube', '')}",
                domain=np.array([[0, 0, 0], [1, 1, 1]])
            )

            # 4. 写入磁盘
            colour.write_LUT(new_lut, str(final_out_path))
            logger.info(f"[成功] {rel_path.parent.name}/{new_name}")
            stats["success"] += 1

        except Exception as e:
            logger.error(f"[失败] 处理 {cube_name} 时发生错误: {e}")
            stats["failed"] += 1

    elapsed_time = time.time() - start_time
    logger.info("=" * 60)
    logger.info(f"处理完成! 耗时: {elapsed_time:.2f} 秒")
    logger.info(f"统计: 成功 {stats['success']} | 跳过 {stats['skipped']} | 失败 {stats['failed']}")
    logger.info(f"导出路径: {output_root}")
    logger.info("=" * 60)


# ---------------------------------------------------------
# 4. CLI 命令行接口
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="富士官方 F-Log2 LUT 转换为索尼 S-Log3 专业工具")

    parser.add_argument("-i", "--input", type=str, default="./Fuji_Official_LUTs",
                        help="包含富士官方 LUT 的根目录路径 (默认: ./Fuji_Official_LUTs)")
    parser.add_argument("--input-colourspace", type=str, default="S-Gamut3.Cine",
                        choices=("S-Gamut3.Cine", "S-Gamut3"),
                        help="Sony S-Log3 素材配套的输入色域 (默认: S-Gamut3.Cine)")
    parser.add_argument("--output-grid-size", type=int, default=None,
                        choices=(33, 65, 129),
                        help="输出 LUT 网格精度 (默认: auto)")

    args = parser.parse_args()

    process_lut_directory(
        input_dir=args.input,
        input_colourspace=args.input_colourspace,
        output_grid_size=args.output_grid_size,
    )

if __name__ == "__main__":
    main()
