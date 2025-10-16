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
import asyncio
import logging

from src.generate_notebooks import generate_notebooks

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


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
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

    asyncio.run(generate_notebooks(**vars(parser.parse_args())))
