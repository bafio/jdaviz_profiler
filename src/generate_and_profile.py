import logging
from os.path import join as os_path_join
from typing import Any

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from src.generate_notebooks import generate_notebooks
from src.profile_notebook import profile_notebook
from src.utils import get_logger

# Initialize logger
logger: logging.Logger = get_logger()


def generate_and_profile(
    input_dir_path: str,
    url: str,
    token: str,
    kernel_name: str,
    headless: bool,
    max_wait_time: int,
    log_screenshots: bool = False,
    save_metrics: bool = False,
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
    max_wait_time : int
        Max time to wait after executing each cell (in minutes).
    log_screenshots : bool, optional
        Whether to log screenshots or not (default: False).
    save_metrics : bool, optional
        Whether to save profiling metrics to a CSV file (default: False).
    """
    logger.debug(
        "Generating and profiling notebooks with "
        f"Input Directory Path: {input_dir_path} -- "
        f"URL: {url} -- "
        f"Token: {token} -- "
        f"Kernel Name: {kernel_name} -- "
        f"Headless: {headless} -- "
        f"Max Wait Time: {max_wait_time} -- "
        f"Log Screenshots: {log_screenshots} -- "
        f"Save Metrics: {save_metrics} -- "
    )

    # Generate notebooks from template
    nb_input_paths: list[str] = generate_notebooks(input_dir_path=input_dir_path)

    # Define optional directories for screenshots and metrics
    screenshots_dir_path: str | None = (
        os_path_join(input_dir_path, "screenshots") if log_screenshots else None
    )
    metrics_dir_path: str | None = (
        os_path_join(input_dir_path, "metrics") if save_metrics else None
    )

    # Set up the partial arguments for the `profile_notebook` call
    profile_notebook_kwargs: dict[str, Any] = {
        "url": url,
        "token": token,
        "kernel_name": kernel_name,
        "headless": headless,
        "max_wait_time": max_wait_time,
        "screenshots_dir_path": screenshots_dir_path,
        "metrics_dir_path": metrics_dir_path,
    }
    progress_bar_kwargs: dict[str, Any] = {
        "iterable": nb_input_paths,
        "desc": "Profiling Notebooks Progress",
        "position": 2,
        "leave": False,
    }

    # Profile each generated notebook
    with logging_redirect_tqdm([logger]):
        for nb_input_path in tqdm(**progress_bar_kwargs):
            logger.info(f"Profiling notebook: {nb_input_path}")
            profile_notebook_kwargs["nb_input_path"] = nb_input_path
            profile_notebook(**profile_notebook_kwargs)
