import logging
from os import makedirs
from os.path import basename, splitext
from os.path import join as os_path_join
from time import gmtime, strftime

from src.jupyterlab_helper import JupyterLabHelper
from src.profiler import Profiler
from src.utils import ProfilerContext, get_logger

# Initialize logger
logger: logging.Logger = get_logger()


def profile_notebook(context: ProfilerContext) -> None:
    """
    Profile the notebook at the specified URL using Selenium.
    Parameters
    ----------
    context : ProfilerContext
        The context containing all necessary parameters for profiling.
    Raises
    ------
    FileNotFoundError
        If the notebook file does not exist.
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    logger.debug(f"Starting profiler with {context}")

    if context.screenshots_dir_path:
        # Create the directory(ies), if not yet created, in where the screenshots
        # will be saved. e.g.: <screenshots_dir_path>/<YYYY_MM_DD>/<nb_filename_wo_ext>/
        context.screenshots_dir_path = os_path_join(
            context.screenshots_dir_path,
            strftime("%Y_%m_%d", gmtime()),
            splitext(basename(context.nb_input_path))[0],
        )
        makedirs(context.screenshots_dir_path, exist_ok=True)

    if context.metrics_dir_path:
        # Create the directory(ies), if not yet created, in where the metrics
        # will be saved. e.g.: <metrics_dir_path>/<YYYY_MM_DD>/<nb_filename_wo_ext>/
        context.metrics_dir_path = os_path_join(
            context.metrics_dir_path,
            strftime("%Y_%m_%d", gmtime()),
            splitext(basename(context.nb_input_path))[0],
        )
        makedirs(context.metrics_dir_path, exist_ok=True)

    # Initialize JupyterLab helper
    jupyterlab_helper: JupyterLabHelper = JupyterLabHelper(context.url, context.token)

    # Prepare JupyterLab environment
    jupyterlab_helper.clear_all_jupyterlab_sessions()
    jupyterlab_helper.restart_kernel(context.kernel_name)
    jupyterlab_helper.upload_notebook(context.nb_input_path)

    try:
        # Start Selenium and run the profiler
        profiler: Profiler = Profiler(context, jupyterlab_helper)
        profiler.run_notebook()
    finally:
        profiler.close()
        # Clean up by deleting the uploaded notebook
        nb_filename = jupyterlab_helper.get_notebook_filename(context.nb_input_path)
        jupyterlab_helper.delete_notebook(nb_filename)
