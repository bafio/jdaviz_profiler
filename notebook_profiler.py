#!/usr/bin/env python3
"""
Uses Selenium to launch and interact with JupyterLab, executing each notebook cell and
recording performance metrics.

Usage:
$> python profiler.py --url <JupyterLab URL> --token <API Token> \
    --kernel_name <kernel name> --nb_input_path <notebook path>
"""

import argparse
import asyncio
import logging

from src.profile_notebook import profile_notebook

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
            "Script that Uses Selenium to launch and interact with JupyterLab, "
            "executing each notebook cell and recording performance metrics."
        )
    )
    parser.add_argument(
        "--url",
        help=(
            "The URL of the JupyterLab instance where the notebook is going to "
            "be profiled."
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
        "--nb_input_path",
        help="Path to the input notebook to be profiled.",
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
        "--screenshots_dir_path",
        help=(
            "Path to the directory to where screenshots will be stored (default: None)."
        ),
        required=False,
        type=str,
        default=None,
    )
    parser.add_argument(
        "--metrics_dir_path",
        help=("Path to the directory to where metrics will be stored (default: None)."),
        required=False,
        type=str,
        default=None,
    )
    parser.add_argument(
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(profile_notebook(**vars(parser.parse_args())))
