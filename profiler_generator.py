#!/usr/bin/env python3
"""
Script to generate a profiler notebook from a template with specified parameters.
This script reads a notebook template, replaces the parameters in the
template with the provided values, and saves the modified notebook.
"""

import argparse
from os import path as os_path
import nbformat


def generate_profiler_notebook(template_path: str, parameters_values: dict
) -> nbformat.NotebookNode:
    """
    Generate a profiler notebook from the template with the specified parameters.
    Parameters
    ----------
    template_path : str
        Path to the notebook template file.
    parameters_values : dict
        Dictionary containing the parameters to replace in the template.
        Expected keys: 'image_pixel_side', 'viewport_pixel_size', 'n_images',
        'sidecar', 'with_dq'.
    Returns
    -------
    nbformat.NotebookNode
        The modified notebook with parameters replaced.
    Raises
    ------
    ValueError
        If no parameters cell is found in the template notebook.
    """

    template_nb = nbformat.read(template_path, nbformat.NO_CONVERT)
    parameters_source = ""

    # Modify the template notebook with the provided parameters
    for cell in template_nb.cells:
        tags = cell.metadata.get("tags", [])
        if "parameters" in tags:
            parameters_source = cell.source
            if not parameters_source:
                raise ValueError("No parameters cell found in the template notebook.")
            cell.source = parameters_source.format(**parameters_values)
            break

    return template_nb



if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = (
            "Script that generates a profiler notebook from a given"
            " notebook template and parameters."
        )
    )
    parser.add_argument(
        "--template_path",
        help = "Path to the notebook template file.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--image_pixel_side",
        help = """image size parameter (in pixels per side)
(500, 1_000, 10_000, 100_000) pixels per side""",
        choices = (500, 1_000, 10_000, 100_000,),
        default = 500,
        required = False,
        type = int,
    )
    parser.add_argument(
        "--viewport_pixel_size",
        help = """viewport size parameter (in pixels)
(600, 1_000, 2_000, 4_000) pixels per side""",
        choices = (600, 1_000, 2_000, 4_000,),
        default = 600,
        required = False,
        type = int,
    )
    parser.add_argument(
        "--n_images",
        help = """number of large images loaded/generated simultaneously and WCS-linked"
(1, 3, 5, 10, 25) images""",
        choices = (1, 3, 5, 10, 25,),
        default = 1,
        required = False,
        type = int,
    )
    parser.add_argument(
        "--sidecar",
        help = """inside/outside of sidecar (True, False) inside/outside of sidecar""",
        choices = (True, False,),
        default = False,
        required = False,
        type = bool,
    )
    parser.add_argument(
        "--with_dq",
        help = """with and without DQ loaded (True, False) with/without DQ""",
        choices = (True, False,),
        default = False,
        required = False,
        type = bool,
    )
    parser.add_argument(
        "--output_path",
        help="Path to save the generated profiler notebook.",
        required=False,
        type=str,
    )
    args = parser.parse_args()

    # If no output path is provided, use the default name
    if not args.output_path:
        args.output_path = (
            "notebooks/profiler_notebook_"
            f"image_pixel_side{args.image_pixel_side}_"
            f"viewport{args.viewport_pixel_size}_"
            f"n_images{args.n_images}_"
            f"sidecar{args.sidecar}_"
            f"with_dq{args.with_dq}"
            ".ipynb"
        )

    current_file_path = os_path.dirname(os_path.abspath(__file__))
    # Resolve the template path relative to the current file's directory
    template_path = os_path.join(current_file_path, args.template_path)
    # Resolve the output path relative to the current file's directory
    output_path = os_path.join(current_file_path, args.output_path)

    # Check if the template file exists
    if not os_path.isfile(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")
    # Ensure the output directory exists
    output_dir = os_path.dirname(output_path)
    if output_dir and not os_path.exists(output_dir):
        raise FileNotFoundError(f"Output directory does not exist: {output_dir}")
    # Check if the output path exists
    if os_path.exists(output_path):
        raise FileExistsError(f"Output file already exists: {output_path}")

    parameters_values = {
        "image_pixel_side_value": args.image_pixel_side,
        "viewport_pixel_size_value": args.viewport_pixel_size,
        "n_images_value": args.n_images,
        "sidecar_value": args.sidecar,
        "with_dq_value": args.with_dq,
    }

    parametrized_nb = generate_profiler_notebook(
        template_path=template_path,
        parameters_values=parameters_values,
    )

    nbformat.write(parametrized_nb, output_path)
