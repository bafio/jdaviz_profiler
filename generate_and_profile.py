#!/usr/bin/env python3
"""
Script to generate the parameterized notebooks from a template.ipynb and params.json and
run the profiler on them.

Usage:
$> python generate_and_profile.py --input_dir_path <usecase path> \
    --url <JupyterLab URL> --token <API Token> --kernel_name <kernel name>
"""

import argparse
import asyncio
import logging

from src.generate_and_profile import generate_and_profile

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Script to generate the profiler notebooks from a template and "
            "run the profiler on them."
        )
    )
    parser.add_argument(
        "--input_dir_path",
        help=(
            "Path to the directory containing the template notebook and params.json "
            "file."
        ),
        required=True,
        type=str,
    )
    parser.add_argument(
        "--url",
        help=(
            "The URL of the JupyterLab instance where the notebook is going to be "
            "profiled."
        ),
        required=True,
        type=str,
    )
    parser.add_argument(
        "--token",
        help="The token to access the JupyterLab instance.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--kernel_name",
        help="The name of the kernel to use for the notebook.",
        required=True,
        type=str,
    )
    parser.add_argument(
        "--headless",
        help="Whether to run in headless mode (default: False).",
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
    )
    parser.add_argument(
        "--log_screenshots",
        help="Whether to log screenshots or not (default: False).",
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
    )
    parser.add_argument(
        "--save_metrics",
        help="Whether to save profiling metrics to a CSV file (default: False).",
        required=False,
        type=bool,
        default=False,
        choices=[True, False],
    )
    parser.add_argument(
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(generate_and_profile(**vars(parser.parse_args())))
