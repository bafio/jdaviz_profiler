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
from os.path import join as os_path_join

from notebook_profiler import profile_notebook
from notebooks_generator import generate_notebooks

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


async def generate_and_profile(
    input_dir_path: str,
    url: str,
    token: str,
    kernel_name: str,
    headless: bool,
    log_screenshots: bool = False,
    log_level: str = "INFO",
) -> None:
    """
    Generate profiler notebooks from a template and run the profiler on them.
    Parameters
    ----------
    input_dir_path : str
        Path to the directory containing the template notebook and params.json file.
    url : str
        The URL of the JupyterLab instance where the notebook is going to be profiled.
    token : str
        The token to access the JupyterLab instance.
    kernel_name : str
        The name of the kernel to use for the notebook.
    headless : bool
        Whether to run in headless mode.
    log_screenshots : bool, optional
        Whether to log screenshots or not (default: False).
    log_level : str, optional
        Set the logging level (default: "INFO").
    """
    # Set up logging
    logger.setLevel(log_level.upper())
    logger.debug(
        "Generating and profiling notebooks with "
        f"Input Directory Path: {input_dir_path} -- "
        f"URL: {url} -- "
        f"Token: {token} -- "
        f"Kernel Name: {kernel_name} -- "
        f"Headless: {headless} -- "
        f"Log Screenshots: {log_screenshots} -- "
        f"Log Level: {log_level}"
    )

    nb_input_paths = generate_notebooks(
        input_dir_path=input_dir_path, log_level=log_level
    )

    if log_screenshots:
        screenshots_dir_path = os_path_join(input_dir_path, "screenshots")
    else:
        screenshots_dir_path = None

    for nb_input_path in nb_input_paths:
        logger.info(f"Profiling notebook: {nb_input_path}")

        await profile_notebook(
            url=url,
            token=token,
            kernel_name=kernel_name,
            nb_input_path=nb_input_path,
            headless=headless,
            screenshots_dir_path=screenshots_dir_path,
            log_level=log_level,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
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
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(generate_and_profile(**vars(parser.parse_args())))
