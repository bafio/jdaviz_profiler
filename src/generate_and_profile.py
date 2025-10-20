import logging
from os.path import join as os_path_join

from src.generate_notebooks import generate_notebooks
from src.profile_notebook import profile_notebook

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


def generate_and_profile(
    input_dir_path: str,
    url: str,
    token: str,
    kernel_name: str,
    headless: bool,
    log_screenshots: bool = False,
    save_metrics: bool = False,
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
    save_metrics : bool, optional
        Whether to save profiling metrics to a CSV file (default: False).
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
        f"Save Metrics: {save_metrics} -- "
        f"Log Level: {log_level}"
    )

    nb_input_paths: list[str] = generate_notebooks(
        input_dir_path=input_dir_path, log_level=log_level
    )
    screenshots_dir_path: str | None = (
        os_path_join(input_dir_path, "screenshots") if log_screenshots else None
    )
    metrics_dir_path: str | None = (
        os_path_join(input_dir_path, "metrics") if save_metrics else None
    )

    for nb_input_path in nb_input_paths:
        logger.info(f"Profiling notebook: {nb_input_path}")

        profile_notebook(
            url=url,
            token=token,
            kernel_name=kernel_name,
            nb_input_path=nb_input_path,
            headless=headless,
            screenshots_dir_path=screenshots_dir_path,
            metrics_dir_path=metrics_dir_path,
            log_level=log_level,
        )
