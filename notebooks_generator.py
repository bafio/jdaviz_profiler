#!/usr/bin/env python3
"""
Script to generate the parameterized notebooks from a template.ipynb and params.json.
The template.ipynb file serves as the base notebook, while params.json contains the
parameter values to be injected into the notebook.
The template.ipynb must have a cell with placeholders for the parameters to be replaced,
therefore this cell must:
    - precede all other cells with actual code using the parameters.
    - be tagged with the "parameters" label.
Each parameter in the params.json file must have a corresponding placeholder in the
template.ipynb file, and the placeholders must be unique having "_value" as suffix,
e.g. `image_pixel_side_value` or `viewport_pixel_size_value`.
The generated parameterized notebooks will be saved in the "notebooks" directory.
An example of how to structure this, and the template.ipynb and params.json files, is
provided in the repository in imviz_images.

Usage:
$> python notebooks_generator.py --input_dir_path <usecase path>
"""

import argparse
import itertools
import logging
import os
from os import path as os_path

import nbformat

from utils import load_dict_from_json_file

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

NOTEBOOK_TEMPLATE_FILENAME = "template.ipynb"
PARAMS_FILENAME = "params.json"
OUTPUT_DIR_PATH = "notebooks"


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


def inject_key_value_data(
    template_nb: nbformat.NotebookNode,
    data_dict: dict,
    cell_tag: str,
) -> nbformat.NotebookNode:
    """
    Inject key-value data into a specific cell (tagged with `cell_tag`) in the template
    notebook.
    Parameters
    ----------
    template_nb : nbformat.NotebookNode
        The template notebook to modify.
    data_dict : dict
        A dictionary of key-value data to inject into the notebook.
    cell_tag : str
        The tag of the cell to modify.
    Returns
    -------
    nbformat.NotebookNode
        The modified notebook with data injected.
    Raises
    ------
    ValueError
        If no cell with the specified tag is found in the template.ipynb.
        If the cell is found with no content in the template.ipynb.
    """
    cell_source = ""
    cell_found = False

    # Modify the template.ipynb with the provided data
    for cell in template_nb.cells:
        # Get the nb cell tagged with the specified cell_tag
        tags = cell.metadata.get("tags", [])
        if cell_tag in tags:
            cell_found = True
            cell_source = cell.source
            if not cell_source:
                msg = "Cell found with no content in the template.ipynb."
                logger.error(msg)
                raise ValueError(msg)
            cell.source = cell_source.format(**data_dict)
            break

    if not cell_found:
        msg = f"No cell with '{cell_tag}' tag found in the template.ipynb."
        logger.error(msg)
        raise ValueError(msg)

    return template_nb


def inject_done_statement(template_nb: nbformat.NotebookNode) -> nbformat.NotebookNode:
    """
    Inject a `print("DONE")` statement at the end of code cells in the template
    notebook.
    Parameters
    ----------
    template_nb : nbformat.NotebookNode
        The template notebook to modify.
    Returns
    -------
    nbformat.NotebookNode
        The modified notebook with data injected.
    """
    done_statement = 'print("DONE")'

    # Modify the template.ipynb with the provided data
    for cell in template_nb.cells:
        # Skip non code type cells
        if cell.cell_type != "code":
            continue
        cell_source = cell.source
        lines = cell_source.splitlines()
        if lines and lines[-1] != done_statement:
            lines.append(done_statement)
        cell.source = os.linesep.join(lines)

    return template_nb


def generate_notebook(
    template_path: str, parameters_values: dict
) -> nbformat.NotebookNode:
    """
    Generate the parameterized notebook from a template.ipynb and a dictionary of
    parameters.
    Parameters
    ----------
    template_path : str
        Path to the template.ipynb file.
    parameters_values : dict
        Dictionary containing the parameters to replace in the template.ipynb.
        Example keys: 'image_pixel_side_value', 'viewport_pixel_size_value'.
    Returns
    -------
    nbformat.NotebookNode
        The modified notebook with parameters replaced.
    Raises
    ------
    ValueError
        If no cell with "parameters" tag is found in the template.ipynb.
        If the parameters cell is found with no content in the template.ipynb.
    """

    template_nb = nbformat.read(template_path, nbformat.NO_CONVERT)

    template_nb = clear_notebook_outputs(template_nb)

    template_nb = inject_key_value_data(
        template_nb=template_nb,
        data_dict=parameters_values,
        cell_tag="parameters",
    )

    template_nb = inject_done_statement(template_nb=template_nb)

    return template_nb


def generate_notebooks(input_dir_path: str, log_level: str = "INFO") -> list[str]:
    """
    Generate the parameterized notebooks from a template.ipynb and params.json, and
    save them to the "notebooks" directory.
    Parameters
    ----------
    input_dir_path : str
        Path to the directory containing the template.ipynb and params.json files.
    log_level : str, optional
        Logging level (default is "INFO").
    Raises
    ------
    FileNotFoundError
        If the template.ipynb does not exist or the params.json file does not exist.
    """
    # Set up logging
    logger.setLevel(log_level.upper())
    logger.debug(
        "Starting notebook generation with "
        f"Input Directory Path: {input_dir_path} -- "
        f"Log Level: {log_level}"
    )

    # Resolve the template.ipynb file path, params file path, and output directory path
    template_path = os_path.join(input_dir_path, NOTEBOOK_TEMPLATE_FILENAME)
    params_path = os_path.join(input_dir_path, PARAMS_FILENAME)
    output_dir_path = os_path.join(input_dir_path, OUTPUT_DIR_PATH)

    # Check if the template.ipynb file exists
    if not os_path.isfile(template_path):
        msg = f"template.ipynb file does not exist: {template_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Check if the params file exists
    if not os_path.isfile(params_path):
        msg = f"Params file does not exist: {params_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Ensure the output directory exists
    if not os_path.isdir(output_dir_path):
        os.makedirs(output_dir_path)

    # Load parameters
    params = load_dict_from_json_file(params_path)

    # Generate all combinations of parameters
    parameters_combinations = dict_combinations(params)

    # Iterate over each combination of parameters and generate the notebooks
    logger.info("Generating profiler notebooks...")

    nb_base_filename = os_path.split(input_dir_path)[-1]
    output_paths = []
    for parameters_values in parameters_combinations:
        # Create the output path for the generated notebook
        nb_filename = nb_base_filename
        for k, v in parameters_values.items():
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
        description=(
            "Script to generate the parameterized notebooks from a template.ipynb and "
            "params.json."
        )
    )
    parser.add_argument(
        "--input_dir_path",
        help=(
            "Path to the directory containing the template.ipynb and params.json files."
        ),
        required=True,
        type=str,
    )
    parser.add_argument(
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    generate_notebooks(**vars(parser.parse_args()))
