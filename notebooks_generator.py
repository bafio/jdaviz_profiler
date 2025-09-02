#!/usr/bin/env python3
"""
Script that generates the profiler notebooks from a given notebook template (template.ipynb) and
a params.yaml file containing the parameters to be replaced in the template.
"""
import argparse
import itertools
import logging
import os
from os import path as os_path

import nbformat
import yaml


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

NOTEBOOK_TEMPLATE_FILENAME = "template.ipynb"
PARAMS_FILENAME = "params.yaml"


def dict_combinations(input_dict: dict) -> list[dict]:
    """
    Generate all combinations of values from a dictionary.
    Parameters
    ----------
    input_dict : dict
        Dictionary containing parameter names and their possible values.
    Returns
    -------
    list of dict
        List of dictionaries, each representing a unique combination of parameters.
    """
    keys, values = input_dict.keys(), input_dict.values()
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def build_parameters_values(params_path: str) -> list[dict]:
    """
    Build a list of dictionaries containing all combinations of parameters based on
    the provided params.yaml file.
    Parameters
    ----------
    params_path : str
        Path to the params.yaml file.
    Returns
    -------
    list of dict
        Each dictionary contains a unique combination of parameters.
    Raises
    ------
    FileNotFoundError
        If the params.yaml file does not exist.
    ValueError
        If the params.yaml file is empty or improperly formatted.
    """
    with open(params_path, "r") as f:
        params = yaml.full_load(f)
    if not params:
        msg = f"No parameters found in {params_path}"
        logger.error(msg)
        raise ValueError(msg)

    parameters_values = dict_combinations(params)

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


def generate_notebook(template_path: str, parameters_values: dict
) -> nbformat.NotebookNode:
    """
    Generate a profiler notebook from the template with the specified parameters.
    Parameters
    ----------
    template_path : str
        Path to the notebook template file.
    parameters_values : dict
        Dictionary containing the parameters to replace in the template.
        Example keys: 'image_pixel_side_value', 'viewport_pixel_size_value', 'n_images_value'.
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


def generate_notebooks(
        input_dir_path: str, output_dir_path: str, log_level: str = "INFO"
) -> list[str]:
    """
    Generate profiler notebooks from a template and a params.yaml file, and save them to
    the specified directory.
    Parameters
    ----------
    input_dir_path : str
        Path to the directory containing the template notebook and params.yaml file.
    output_dir_path : str
        Directory where the generated notebooks will be saved.
    log_level : str, optional
        Logging level (default is "INFO").
    Raises
    ------
    FileNotFoundError
        If the template file does not exist or the output directory does not exist.
    """
    # Set up logging
    logger.setLevel(log_level.upper())

    # Resolve the template path and params path
    template_path = os_path.join(input_dir_path, NOTEBOOK_TEMPLATE_FILENAME)
    params_path = os_path.join(input_dir_path, PARAMS_FILENAME)

    # Resolve the output path
    output_dir_path = os_path.join(input_dir_path, output_dir_path)

    # Check if the template file exists
    if not os_path.isfile(template_path):
        msg = f"Template file does not exist: {template_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Check if the params file exists
    if not os_path.isfile(params_path):
        msg = f"Params file does not exist: {params_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Ensure the output directory exists
    if not os_path.isdir(output_dir_path):
        msg = f"Output directory does not exist: {output_dir_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Generate all combinations of parameters
    parameters_combinations = build_parameters_values(params_path)

    # Iterate over each combination of parameters and generate the notebook
    logger.info("Generating profiler notebooks...")

    nb_base_filename = os_path.split(input_dir_path)[-1]
    output_paths = []
    for parameters_values in parameters_combinations:
        # Create the output path for the generated notebook
        nb_filename = nb_base_filename
        for k,v in parameters_values.items():
            nb_filename = f"{nb_filename}-{k.removesuffix('_value')}{v}"
        nb_filename = f"{nb_filename}.ipynb"
        output_path = os_path.join(output_dir_path, nb_filename)

        # Check if the output path already exists, if so remove the file
        try:
            os_path.exists(output_path) and os.remove(output_path)
        except OSError as e:
            logger.error(f"Error removing existing file {output_path}: {e}")
            continue

        # Generate the notebook with proper parameters
        parametrized_nb = generate_notebook(
            template_path=template_path,
            parameters_values=parameters_values,
        )

        # Write the modified notebook to the output path
        nbformat.write(parametrized_nb, output_path)
        output_paths.append(output_path)

    logger.info(f"Total notebooks generated: {len(output_paths)}")
    logger.info("Profiler notebooks generation completed.")

    return output_paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = (
            "Script that generates the profiler notebooks from a given notebook "
            "template (template.ipynb) and a params.yaml file containing the parameters "
            "to be replaced in the template."
        )
    )
    parser.add_argument(
        "--input_dir_path",
        help = "Path to the directory containing the template notebook and params.yaml file.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--output_dir_path",
        help="Path to save the generated profiler notebooks.",
        required=False,
        type=str,
        default="notebooks",
    )
    parser.add_argument(
        "--log_level",
        help="Set the logging level (default: INFO).",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    generate_notebooks(**vars(parser.parse_args()))
