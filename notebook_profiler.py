#!/usr/bin/env python3
"""
Uses Playwright to launch and interact with JupyterLab, executing each notebook cell and
recording performance metrics.

Usage:
$> python profiler.py --url <JupyterLab URL> --token <API Token> --kernel_name <kernel name> \
    --nb_input_path <notebook path>
"""

import argparse
import asyncio
import json
import logging
import re
import requests
import time
from collections import OrderedDict
# from io import BytesIO
from os import path as os_path

from playwright.async_api import async_playwright, ElementHandle
from playwright.async_api._context_manager import PlaywrightContextManager
# from PIL import Image

from utils import load_dict_from_yaml_file


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


class Profiler:
    """Class to profile a Jupyter notebook using Playwright."""

    # Key in the configs dict that contains the RGB border color triplet value
    RGB_BORDER_COLOR_TRIPLET_KEY = "rgb_border_color_triplet_value"

    # The width and height to set for the browser viewport to make the page really tall
    # to avoid scrollbars and scrolling issues
    VIEWPORT_SIZE = {"width": 1600, "height": 20000}

    # CSS style to disable the pulsing animation that can interfere with screenshots taking
    PAGE_STYLE_TAG_CONTENT = ".viewer-label.pulse {animation: none !important;}"

    # Selector for the notebook element
    NB_SELECTOR = ".jp-Notebook"

    # Selector for all code cells in the notebook
    NB_CELLS_SELECTOR = ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"

    # Selector for all output cells in a code cell
    OUTPUT_CELLS_SELECTOR = ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"

    # Selector for all text output cells in a code cell
    OUTPUT_CELLS_TEXT_SELECTOR = ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"

    # Regex to identify the cell output containing the time elapsed information
    CELL_OUTPUT_REGEX = r'^.*cell\stime\selapsed:\s(?P<time_elapsed>\d+\.\d+)$'


    def __init__(
            self, playwright: PlaywrightContextManager, url: str, headless: str, max_wait_time: int,
            configs: dict
        ) -> None:
        """
        Initialize the Profiler with Playwright, URL, headless mode, wait time, and configurations.
        Parameters
        ----------
        playwright : PlaywrightContextManager
            The Playwright context manager.
        url : str
            The URL of the notebook to profile.
        headless : bool
            Whether to run in headless mode.
        max_wait_time : int
            Time to wait after executing each cell (in seconds).
        configs : dict
            Dictionary containing the configurations for the notebook.
        """
        self.playwright = playwright
        self.url = url
        self.headless = headless
        self.max_wait_time = max_wait_time
        self.configs = configs
        self.viz_cell = None
        self.browser = None
        self.context = None
        self.page = None
        self.nb_cells = OrderedDict()
        self.nb_cells_execution_times = OrderedDict()
        self.viz_cell_regex = fr"border-color: rgb\({self.configs[self.RGB_BORDER_COLOR_TRIPLET_KEY]}\)"  # noqa


    async def setup(self) -> None:
        """
        Set up the Playwright browser and page.
        """
        # Launch the browser and create a new page
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()
        self.page = await self.context.new_page()

        # Apply custom viewport size
        await self.page.set_viewport_size(self.VIEWPORT_SIZE)
        logger.debug("Page viewport set")

        # Navigate to the notebook URL
        logger.info(f"Navigating to {self.url}")
        await self.page.goto(self.url)

        # Apply custom CSS styles
        await self.page.add_style_tag(content=self.PAGE_STYLE_TAG_CONTENT)
        logger.debug("Page style added")


    async def run(self) -> None:
        """
        Run the profiling process.
        """
        # Wait for the notebook to load
        await self.page.wait_for_selector(self.NB_SELECTOR)

        # Wait a bit to ensure the page is fully loaded
        sleep_time = 5
        logger.info(f"Sleeping {sleep_time} seconds to ensure full load...")
        await asyncio.sleep(sleep_time)

        # Collect cells to execute
        await self.collect_nb_cells()

        # Start profiling
        logger.info("Starting profiling...")

        sleep_time = 2
        # Execute each cell and wait for outputs
        for nb_cell_item in self.nb_cells.items():
            await self.execute_cell(nb_cell_item)
            # Wait a bit to ensure stability before moving to the next cell
            logger.info(f"Sleeping {sleep_time} seconds to ensure stability...")
            await asyncio.sleep(sleep_time)

        logger.info(f"Cells execution times: {sum(self.nb_cells_execution_times.values())}")
        logger.info("Profiling completed.")


    async def execute_cell(self, cell_item: tuple[int, ElementHandle]) -> None:
        """
        Execute a code cell in the notebook.
        """
        cell_index, cell = cell_item
        try:
            logger.info(f"Executing cell {cell_index}")
            # Focus on the cell
            await cell.focus()
            # Execute the cell
            await self.page.keyboard.press('Shift+Enter')
            # Initialize variables to track the viz cell and elapsed time
            viz_cell_is_stable, timer, time_elapsed = False, time.time(), 0

            output_cells = None
            while time_elapsed < self.max_wait_time:
                # If we have the viz cell, check if it's stable
                if self.viz_cell:
                    logger.debug("We already have the viz cell, checking if it's stable...")
                    viz_cell_is_stable = await self.is_viz_cell_stable()
                    logger.debug(f"viz_cell_is_stable: {viz_cell_is_stable}")
                    if viz_cell_is_stable:
                        # If the viz cell is stable, we can stop looping, take the time and move on
                        logger.debug("Viz cell is stable, stopping the wait loop...")
                        time_elapsed = time.time() - timer
                        await self.save_time_elapsed(cell_index, time_elapsed, viz_cell_is_stable)
                        return
                else:
                    # Wait a bit before checking again
                    logger.debug("Waiting for the output cells to appear...")
                    await asyncio.sleep(0.5)
                    # Look for the viz cell in the outputs of the current cell
                    output_cells = await cell.query_selector_all(self.OUTPUT_CELLS_SELECTOR)
                    logger.debug(f"Found {len(output_cells)} output cells")
                    # if we found output cells, look for the viz cell among them
                    if output_cells:
                        logger.debug("Looking for the viz cell among the output cells...")
                        await self.detect_viz_cell(output_cells)
                # In this case, if we don't have a viz cell or we have a not stable viz cell,
                # we take the time elapsed and check if we reached the max wait time
                time_elapsed = time.time() - timer

            # save time elapsed from the output cells
            await self.save_time_elapsed(
                cell_index, time_elapsed, viz_cell_is_stable, output_cells
            )

        except Exception as e:
            logger.exception(f"An error occurred while executing cell {cell_index}: {e}")


    async def save_time_elapsed(
            self, cell_index: int, time_elapsed: float, viz_cell_is_stable: bool,
            output_cells: list[ElementHandle] = None) -> None:
        """
        Save the time elapsed for a cell execution.
        Parameters
        ----------
        cell_index : int
            The index of the cell.
        time_elapsed : float
            The time elapsed for the cell execution.
        viz_cell_is_stable : bool
            Whether the viz cell is stable.
        output_cells : list[ElementHandle], optional
            The list of output cell elements (default is None).
        """
        if not viz_cell_is_stable and output_cells:
            # try to gather time elapsed from the cell output
            logger.debug("Trying to gather time elapsed from the cell output...")
            logger.debug(f"Found {len(output_cells)} output cells")
            # filter to only text outputs
            text_output_cells = await output_cells[0].query_selector_all(
                self.OUTPUT_CELLS_TEXT_SELECTOR
            )
            logger.debug(f"Found {len(text_output_cells)} text output cells")
            if text_output_cells:
                output_txt = await text_output_cells[0].inner_text()
                match = re.search(self.CELL_OUTPUT_REGEX, output_txt)
                if match:
                    time_elapsed = float(match.group("time_elapsed"))

        self.nb_cells_execution_times[cell_index] = time_elapsed
        # Log the time elapsed for the cell execution
        logger.info(f"Cell {cell_index} completed in {time_elapsed:.2f} seconds")


    async def detect_viz_cell(self, output_cells: list[ElementHandle]) -> None:
        """
        Detect the viz cell from the list of output cells.
        Parameters
        ----------
        output_cells : list[ElementHandle]
            The list of output cell elements.
        """
        # Look for the viz cell among the output cells
        for output_cell in output_cells:
            # Check if the output cell is visible
            output_cell_is_visible = await output_cell.is_visible()
            # If the output cell is not visible, skip it
            if not output_cell_is_visible:
                continue
            # Look for the viz cell by checking the style attribute of its children
            children = await output_cell.query_selector_all("*")
            for child in children:
                style = await child.get_attribute("style")
                if style and re.search(self.viz_cell_regex, style):
                    # We found the viz cell, store it and return
                    self.viz_cell = output_cell
                    logger.debug("Viz cell detected")
                    return


    async def is_viz_cell_stable(self) -> bool:
        """
        Check if the viz cell is stable (i.e., not changing).
        Returns
        -------
        bool
            True if the viz cell is stable, False otherwise.
        """
        # Take a screenshot of the viz cell
        screenshot1 = await self.viz_cell.screenshot()

        # Wait a short period before taking another screenshot
        await asyncio.sleep(0.5)

        # Take another screenshot of the viz cell
        screenshot2 = await self.viz_cell.screenshot()

        # image1 = Image.open(BytesIO(screenshot1))
        # image2 = Image.open(BytesIO(screenshot2))
        # image1.save("screenshot1.png")
        # image2.save("screenshot2.png")

        # Compare the two screenshots
        screenshots_are_the_same = screenshot1 == screenshot2
        logger.debug(f"screenshots_are_the_same: {screenshots_are_the_same}")
        return screenshots_are_the_same


    async def collect_nb_cells(self) -> None:
        """
        Collect all code cells in the notebook and store them in an ordered dictionary.
        """
        # Collect all code cells in the notebook
        nb_cells = await self.page.query_selector_all(self.NB_CELLS_SELECTOR)

        # Store cells in an ordered dictionary with their index
        self.nb_cells = OrderedDict(zip(range(1, len(nb_cells)+1), nb_cells))
        logger.info(f"Number of cells in the notebook: {len(self.nb_cells)}")


    async def close(self) -> None:
        """
        Close the Playwright browser and context.
        """
        await self.context.close()
        logger.debug("Browser context closed")
        await self.browser.close()
        logger.debug("Browser closed")


class JupyterLabHelper:
    """Helper class to interact with JupyterLab."""

    def __init__(self, url: str, token: str, kernel_name: str, nb_input_path: str) -> None:
        self.url = url
        self.token = token
        self.kernel_name = kernel_name
        self.nb_input_path = nb_input_path
        self.headers = {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        }
        self.notebook_url = (
            f"{self.url}/lab/tree/{self.nb_input_path.split('/')[-1]}/"
            f"?token={self.token}"
        )


    async def clear_jupyterlab_sessions(self) -> None:
        """
        Clear all active sessions (notebooks, consoles, terminals) in the JupyterLab instance.
        Raises
        ------
        requests.exceptions.RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get a list of all running sessions
            sessions_url = f"{self.url}/api/sessions"
            response = requests.get(sessions_url, headers=self.headers)
            response.raise_for_status()
            sessions = response.json()

            if not sessions:
                logger.info("No active sessions found.")
                return

            logger.info(f"Found {len(sessions)} active sessions. Shutting them down...")

            # Shut down each session
            for session in sessions:
                session_id = session['id']
                shutdown_url = f"{self.url}/api/sessions/{session_id}"
                shutdown_response = requests.delete(shutdown_url, headers=self.headers)
                shutdown_response.raise_for_status()

                # Print a status message based on the session type
                if 'kernel' in session and session['kernel']:
                    logger.info(
                        "Shut down notebook/console session: "
                        f"{session['path']} (ID: {session_id})"
                    )
                elif 'terminal' in session:
                    logger.info(f"Shut down terminal session: {session['name']} (ID: {session_id})")
                else:
                    logger.info(f"Shut down unknown session type (ID: {session_id})")

        except requests.exceptions.RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e


    async def restart_kernel(self) -> None:
        """
        Restart the kernel for a given kernel name.
        Raises
        ------
        requests.exceptions.RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get the list of all kernels
            kernels_url = f"{self.url}/api/kernels"
            response = requests.get(kernels_url, headers=self.headers)
            response.raise_for_status()
            kernels = response.json()

            # Find the kernel ID for the given kernel name
            kernel_id = None
            for kernel in kernels:
                if kernel['name'] == self.kernel_name:
                    kernel_id = kernel['id']
                    break

            if not kernel_id:
                logger.warning(f"No active kernel found for kernel name: {self.kernel_name}.")
                return

            # Restart the kernel
            restart_url = f"{self.url}/api/kernels/{kernel_id}/restart"
            restart_response = requests.post(restart_url, headers=self.headers)
            restart_response.raise_for_status()

            logger.info(f"Kernel {self.kernel_name} restarted successfully.")

        except requests.exceptions.RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e


    async def upload_notebook(self) -> None:
        """
        Upload the notebook to the JupyterLab instance.
        Raises
        ------
        FileNotFoundError
            If the notebook file does not exist.
        requests.exceptions.RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            notebook_path = self.nb_input_path.split('/')[-1]  # Extract filename from path
            upload_url = f"{self.url}/api/contents/{notebook_path}"
            logger.info(f"Uploading notebook to {upload_url}")

            with open(self.nb_input_path, 'r', encoding='utf-8') as nb_file:
                notebook_content = json.load(nb_file)

            payload = {
                "content": notebook_content,
                "type": "notebook",
                "format": "json"
            }

            response = requests.put(upload_url, headers=self.headers, json=payload)
            response.raise_for_status()

            logger.info(f"Notebook uploaded successfully to {upload_url}")

        except FileNotFoundError as e:
            logger.exception(f"Notebook file not found: {notebook_path}")
            raise e
        except requests.exceptions.RequestException as e:
            logger.exception(f"Error uploading notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e


    async def delete_notebook(self) -> None:
        """
        Delete the notebook from the JupyterLab instance.
        Raises
        ------
        requests.exceptions.RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            notebook_path = self.nb_input_path.split('/')[-1]  # Extract filename from path
            delete_url = f"{self.url}/api/contents/{notebook_path}"
            logger.info(f"Deleting notebook at {delete_url}")

            response = requests.delete(delete_url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Notebook deleted successfully from {delete_url}")

        except requests.exceptions.RequestException as e:
            logger.exception(f"Error deleting notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e


async def profile_notebook(
        url: str, token: str, kernel_name: str, nb_input_path: str, headless: bool,
        max_wait_time: int, configs_path: str, log_level: str = "INFO"
) -> None:
    """
    Profile the notebook at the specified URL using Playwright.
    Parameters
    ----------
    url : str
        The URL of the JupyterLab instance where the notebook is going to be profiled.
    token : str
        The token to access the JupyterLab instance.
    kernel_name : str
        The name of the kernel to use for the notebook.
    nb_input_path : str
        Path to the input notebook to be profiled.
    headless : bool
        Whether to run in headless mode.
    max_wait_time : int
        Max time to wait after executing each cell (in seconds).
    configs_path : str
        Path to the configs.yaml file.
    log_level : str, optional
        Set the logging level (default: INFO).
    Raises
    ------
    FileNotFoundError
        If the notebook file does not exist.
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    # Set up logging
    logger.setLevel(log_level.upper())
    logger.debug(
        "Starting profiler with "
        f"URL: {url} -- "
        f"Token: {token} -- "
        f"Kernel Name: {kernel_name} -- "
        f"Input Notebook Path: {nb_input_path} -- "
        f"Headless: {headless} -- "
        f"Max Wait Time: {max_wait_time} -- "
        f"Configs Path: {configs_path} -- "
        f"Log Level: {log_level}"
    )

    # Check if the configs file exists, load configurations, else no sweat
    if os_path.isfile(configs_path):
        configs = load_dict_from_yaml_file(configs_path)
        logger.debug(f"Loaded configs: {configs}")
    else:
        configs = None
        logger.warning(f"Configs file does not exist: {configs_path}")

    # Initialize JupyterLab helper and clear any existing sessions
    jupyter_lab_helper = JupyterLabHelper(
        url=url,
        token=token,
        kernel_name=kernel_name,
        nb_input_path=nb_input_path,
    )
    await jupyter_lab_helper.clear_jupyterlab_sessions()
    await jupyter_lab_helper.restart_kernel()
    await jupyter_lab_helper.upload_notebook()

    # Start Playwright and run the profiler
    async with async_playwright() as p:
        profiler = Profiler(
            playwright=p,
            url=jupyter_lab_helper.notebook_url,
            headless=headless,
            max_wait_time=max_wait_time,
            configs=configs,
        )
        await profiler.setup()
        await profiler.run()
        await profiler.close()

    # Clean up by deleting the uploaded notebook
    await jupyter_lab_helper.delete_notebook()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = (
            "Script that Uses Playwright to launch and interact with JupyterLab, "
            "executing each notebook cell and recording performance metrics."
        )
    )
    parser.add_argument(
        "--url",
        help = "The URL of the JupyterLab instance where the notebook is going to be profiled.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--token",
        help = "The token to access the JupyterLab instance.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--kernel_name",
        help = "The name of the kernel to use for the notebook.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--nb_input_path",
        help = "Path to the input notebook to be profiled.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--headless",
        help = "Whether to run in headless mode (default: False).",
        required = False,
        type = bool,
        default = False,
        choices = [True, False],
    )
    parser.add_argument(
        "--max_wait_time",
        help = "Max time to wait after executing each cell (in seconds, default: 10).",
        required = False,
        type = int,
        default = 10,
    )
    parser.add_argument(
        "--configs_path",
        help = "Path to the configs.yaml file.",
        required = False,
        type = str,
        default="configs.yaml",
    )
    parser.add_argument(
        "--log_level",
        help = "Set the logging level (default: INFO).",
        default = "INFO",
        choices = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(profile_notebook(**vars(parser.parse_args())))
