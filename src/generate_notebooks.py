import logging
from pathlib import Path
from typing import Any

from src.notebook_generator import NotebookGenerator
from src.utils import dict_combinations, get_logger, load_dict_from_json_file

# Initialize logger
logger: logging.Logger = get_logger()

NOTEBOOK_TEMPLATE_FILENAME: str = "template.ipynb"
PARAMS_FILENAME: str = "params.json"
OUTPUT_DIR_PATH: str = "notebooks"


def generate_notebooks(input_dir_path: Path) -> list[Path]:
    """
    Generate the parameterized notebooks from a template.ipynb and params.json, and
    save them to the "notebooks" directory.
    Parameters
    ----------
    input_dir_path : Path
        Path to the directory containing the template.ipynb and params.json files.
    Raises
    ------
    FileNotFoundError
        If the template.ipynb does not exist or the params.json file does not exist.
    """
    logger.debug(
        f"Starting notebook generation with Input Directory Path: {input_dir_path}"
    )

    # Resolve the template.ipynb file path, params file path, and output directory path
    template_path: Path = input_dir_path / NOTEBOOK_TEMPLATE_FILENAME
    params_path: Path = input_dir_path / PARAMS_FILENAME
    output_dir_path: Path = input_dir_path / OUTPUT_DIR_PATH

    # Check if the template.ipynb file exists
    if not template_path.exists():
        raise FileNotFoundError(
            f"{NOTEBOOK_TEMPLATE_FILENAME} file does not exist in {input_dir_path}"
        )

    # Check if the params file exists
    if not params_path.exists():
        raise FileNotFoundError(
            f"{PARAMS_FILENAME} file does not exist in {input_dir_path}"
        )

    # Ensure the output directory exists
    output_dir_path.mkdir(parents=True, exist_ok=True)

    # Load parameters
    params: dict[str, Any] = load_dict_from_json_file(params_path)

    # Generate all combinations of parameters
    parameters_combinations: list[dict[str, Any]] = dict_combinations(params)

    # Iterate over each combination of parameters and generate the notebooks
    logger.info("Generating profiler notebooks...")

    # Initialize the NotebookGenerator
    notebook_generator = NotebookGenerator(template_path=template_path)
    nb_base_filename: str = input_dir_path.stem
    output_paths: list[Path] = []
    for parameters_values in parameters_combinations:
        # Create the output path for the generated notebook
        nb_filename: str = nb_base_filename
        for k, v in parameters_values.items():
            nb_filename = f"{nb_filename}-{k.removesuffix('_value')}{v}"
        nb_filename = f"{nb_filename}.ipynb"
        output_path: Path = output_dir_path / nb_filename

        # Remove the output path if exists
        output_path.unlink(missing_ok=True)

        # Generate the notebook
        notebook_generator.generate_and_save(
            parameters_values=parameters_values,
            output_path=output_path,
        )

        # Append the output path to the list
        output_paths.append(output_path)

    logger.info(
        "Notebooks generation completed. "
        f"Total notebooks generated: {len(output_paths)}."
    )

    return output_paths
