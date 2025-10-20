import logging
import os
from os import path as os_path
from typing import Any

from src.notebook_generator import NotebookGenerator
from src.utils import dict_combinations, load_dict_from_json_file

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

NOTEBOOK_TEMPLATE_FILENAME: str = "template.ipynb"
PARAMS_FILENAME: str = "params.json"
OUTPUT_DIR_PATH: str = "notebooks"


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
    template_path: str = os_path.join(input_dir_path, NOTEBOOK_TEMPLATE_FILENAME)
    params_path: str = os_path.join(input_dir_path, PARAMS_FILENAME)
    output_dir_path: str = os_path.join(input_dir_path, OUTPUT_DIR_PATH)

    # Check if the template.ipynb file exists
    if not os_path.isfile(template_path):
        msg: str = f"template.ipynb file does not exist: {template_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Check if the params file exists
    if not os_path.isfile(params_path):
        msg: str = f"Params file does not exist: {params_path}"
        logger.error(msg)
        raise FileNotFoundError(msg)

    # Ensure the output directory exists
    if not os_path.isdir(output_dir_path):
        os.makedirs(output_dir_path)

    # Load parameters
    params: dict[str, Any] = load_dict_from_json_file(params_path)

    # Generate all combinations of parameters
    parameters_combinations: list[dict[str, Any]] = dict_combinations(params)

    # Iterate over each combination of parameters and generate the notebooks
    logger.info("Generating profiler notebooks...")

    nb_base_filename: str = os_path.split(input_dir_path)[-1]
    output_paths: list[str] = []
    for parameters_values in parameters_combinations:
        # Create the output path for the generated notebook
        nb_filename: str = nb_base_filename
        for k, v in parameters_values.items():
            nb_filename: str = f"{nb_filename}-{k.removesuffix('_value')}{v}"
        nb_filename = f"{nb_filename}.ipynb"
        output_path: str = os_path.join(output_dir_path, nb_filename)

        # Check if the output path already exists, if so remove the file
        try:
            os_path.exists(output_path) and os.remove(output_path)
        except OSError as e:
            logger.error(f"Error removing existing file {output_path}: {e}")
            continue

        # Generate the notebook
        NotebookGenerator(
            template_path=template_path,
            output_path=output_path,
            parameters_values=parameters_values,
        ).generate()

        output_paths.append(output_path)

    logger.info(f"Total notebooks generated: {len(output_paths)}")
    logger.info("Profiler notebooks generation completed.")

    return output_paths
