#!/usr/bin/env python3
"""
Script to generate the profiler notebooks from a template.
This script reads a notebook template, replaces the parameters in the
template with the proper values, and saves the modified notebooks.
"""
import argparse
import logging
import os
from os import path as os_path

import nbformat


logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


def build_parameters_values():
    """
    Build a list of dictionaries containing all combinations of parameters
    for generating profiler notebooks.
    Returns
    -------
    list of dict
        Each dictionary contains a unique combination of parameters.
    """
    image_pixel_side_values = (500,)# 1_000, 10_000, 100_000)
    viewport_pixel_size_values = (600,)# 1_000, 2_000, 4_000)
    n_images_values = (1,)# 3, 5, 10, 25)
    sidecar_values = (True,)# False)
    with_dq_values = (False,)# True)

    parameters_values = []
    for image_pixel_side in image_pixel_side_values:
        for viewport_pixel_size in viewport_pixel_size_values:
            for n_images in n_images_values:
                for sidecar in sidecar_values:
                    for with_dq in with_dq_values:
                        parameters_values.append({
                            "image_pixel_side_value": image_pixel_side,
                            "viewport_pixel_size_value": viewport_pixel_size,
                            "n_images_value": n_images,
                            "sidecar_value": sidecar,
                            "with_dq_value": with_dq,
                        })

    return parameters_values


def clear_notebook_outputs(notebook: nbformat.NotebookNode) -> nbformat.NotebookNode:
    """
    Clear the outputs of all cells in a notebook.
    Parameters
    ----------
    notebook : nbformat.NotebookNode
        The notebook from which to clear outputs.
    Returns
    -------
    nbformat.NotebookNode
        The notebook with cleared outputs.
    """
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    return notebook


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
        Expected keys: 'image_pixel_side_value', 'viewport_pixel_size_value', 'n_images_value',
        'sidecar_value', 'with_dq_value'.
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

    template_nb = clear_notebook_outputs(template_nb)

    parameters_source = ""

    # Modify the template notebook with the provided parameters
    for cell in template_nb.cells:
        # Get the nb cell tagged as "paramerets"
        tags = cell.metadata.get("tags", [])
        if "parameters" in tags:
            parameters_source = cell.source
            if not parameters_source:
                msg = "Parameters cell is empty in the template notebook."
                logger.error(msg)
                raise ValueError(msg)
            cell.source = parameters_source.format(**parameters_values)
            break

    return template_nb


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = "Script that generates the profiler notebooks from a given notebook template."
    )
    parser.add_argument(
        "--template_path",
        help = "Path to the notebook template file.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--output_dir_path",
        help="Path to save the generated profiler notebooks.",
        required=False,
        type=str,
    )
    parser.add_argument(
        "--log_level",
        help="Set the logging level (default: INFO).",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    args = parser.parse_args()

    # Set up logging
    logger.setLevel(args.log_level.upper())

    # If no output path is provided, use the default name
    if not args.output_dir_path:
        args.output_dir_path = "notebooks"

    current_file_path = os_path.dirname(os_path.abspath(__file__))

    # Resolve the template path relative to the current file's directory
    template_path = os_path.join(current_file_path, args.template_path)

    # Resolve the output path relative to the current file's directory
    output_dir_path = os_path.join(current_file_path, args.output_dir_path)

    # Check if the template file exists
    if not os_path.isfile(template_path):
        msg = f"Template file does not exist: {template_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Ensure the output directory exists
    if not os_path.isdir(output_dir_path):
        msg = f"Output directory does not exist: {output_dir_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Generate all combinations of parameters
    parameters_combinations = build_parameters_values()

    # Iterate over each combination of parameters and generate the notebook
    logger.info("Generating profiler notebooks...")

    nb_generated_counter = 0
    for parameters_values in parameters_combinations:
        # Create the output path for the generated notebook
        nb_filename = (
            "profiler_notebook_"
            f"image_pixel_side{parameters_values['image_pixel_side_value']}_"
            f"viewport{parameters_values['viewport_pixel_size_value']}_"
            f"n_images{parameters_values['n_images_value']}_"
            f"sidecar{parameters_values['sidecar_value']}_"
            f"with_dq{parameters_values['with_dq_value']}"
            ".ipynb"
        )
        output_path = os_path.join(output_dir_path, nb_filename)

        # Check if the output path already exists, if so remove the file
        try:
            os_path.exists(output_path) and os.remove(output_path)
        except OSError as e:
            logger.error(f"Error removing existing file {output_path}: {e}")
            continue

        # Generate the notebook with proper parameters
        parametrized_nb = generate_profiler_notebook(
            template_path=template_path,
            parameters_values=parameters_values,
        )

        # Write the modified notebook to the output path
        nbformat.write(parametrized_nb, output_path)

        nb_generated_counter += 1

    logger.info(f"Total notebooks generated: {nb_generated_counter}")
    logger.info("Profiler notebooks generation completed.")
