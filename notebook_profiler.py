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
import requests
from io import BytesIO
from os import makedirs
from os.path import basename, join as os_path_join, splitext
from time import gmtime, perf_counter_ns, strftime, time

from playwright.async_api import async_playwright, ElementHandle
from playwright.async_api._context_manager import PlaywrightContextManager
from playwright.async_api._generated import Browser, BrowserContext, Page
from PIL import Image


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


class VizElement:
    """Class representing the viz element in a Jupyter notebook."""

    def __init__(self, element: ElementHandle, profiler: "Profiler") -> None:
        """
        Initialize the VizElement with a Playwright ElementHandle.
        Parameters
        ----------
        element : ElementHandle
            The Playwright ElementHandle representing the viz element.
        profiler : Profiler
            The Profiler instance.
        """
        self._element = element
        self._profiler = profiler


    @property
    def element(self) -> ElementHandle:
        return self._element


    @property
    def profiler(self) -> "Profiler":
        return self._profiler


    async def is_stable(self, cell_index: int) -> bool:
        """
        Check if the viz element is stable (i.e., not changing).
        Returns
        -------
        bool
            True if the viz element is stable, False otherwise.
        """
        if self.element is None:
            logger.debug("Viz element element is None, cannot be stable")
            return False

        # Take a screenshot of the viz element
        screenshot_before = await self.element.screenshot()

        # Wait a short period before taking another screenshot
        await asyncio.sleep(0.5)

        # Take another screenshot of the viz element
        screenshot_after = await self.element.screenshot()

        # Log screenshots
        await self.profiler.log_screenshots(cell_index, [screenshot_before, screenshot_after])

        # Compare the two screenshots
        screenshots_are_the_same = screenshot_before == screenshot_after
        logger.debug(f"screenshots_are_the_same: {screenshots_are_the_same}")
        return screenshots_are_the_same


class ExecutableCell:
    """Class representing an executable cell in a Jupyter notebook."""

    def __init__(self, cell: ElementHandle, index: int, profiler: "Profiler") -> None:
        """
        Initialize the ExecutableCell with a Playwright ElementHandle and an optional index.
        Parameters
        ----------
        cell : ElementHandle
            The Playwright ElementHandle representing the cell.
        index : int
            The index of the cell.
        profiler : Profiler
            The Profiler instance.
        """
        self._cell = cell
        self._index = index
        self._profiler = profiler
        self.execution_time = 0


    @property
    def cell(self) -> ElementHandle:
        return self._cell


    @property
    def index(self) -> int:
        return self._index


    @property
    def profiler(self) -> "Profiler":
        return self._profiler


    async def execute(self) -> None:
        try:
            logger.info(f"Executing cell {self.index}")
            # Focus on the cell
            await self.cell.focus()
            # Execute the cell
            await self.profiler.page.keyboard.press('Shift+Enter')
            # Initialize variables to track the viz element and elapsed time
            viz_is_stable, timer, time_elapsed = False, time(), 0

            # output_cells = None
            while time_elapsed < self.profiler.max_wait_time and not viz_is_stable:
                # If we have the viz element, check if it's stable
                if self.profiler.viz_element:
                    logger.debug("We already have the viz element, checking if it's stable...")
                    viz_is_stable = await self.profiler.viz_element.is_stable(self.index)
                else:
                    # Wait a bit before checking again
                    logger.debug("Waiting for the viz element to appear...")
                    await asyncio.sleep(0.5)
                    # Look for the viz element in the page
                    logger.debug("Looking for the viz element in the page...")
                    await self.profiler.detect_viz_element()
                time_elapsed = time() - timer

            # save time elapsed only if coming from a stable viz element, otherwise count as 0
            self.execution_time = time_elapsed if viz_is_stable else 0
            # Log the time elapsed for the cell execution
            logger.info(f"Cell {self.index} completed in {self.execution_time:.2f} seconds")

        except Exception as e:
            logger.exception(f"An error occurred while executing cell {self.index}: {e}")


class Profiler:
    """Class to profile a Jupyter notebook using Playwright."""

    # The width and height to set for the browser viewport to make the page really tall
    # to avoid scrollbars and scrolling issues
    VIEWPORT_SIZE = {"width": 1600, "height": 20000}

    # CSS style to disable the pulsing animation that can interfere with screenshots taking
    PAGE_STYLE_TAG_CONTENT = ".viewer-label.pulse {animation: none !important;}"

    # Selector for the notebook element
    NB_SELECTOR = ".jp-Notebook"

    # Selector for all code cells in the notebook
    NB_CELLS_SELECTOR = ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"

    # Selector for the jdaviz app viz element
    VIZ_ELEMENT_SELECTOR = ".jdaviz.imviz"


    def __init__(
            self, playwright: PlaywrightContextManager, url: str, headless: str, max_wait_time: int,
            screenshots_dir_path: str = None
        ) -> None:
        """
        Initialize the Profiler with Playwright, URL, headless mode, and wait time.
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
        screenshots_dir_path : str, optional
            Path to the directory to where screenshots will be stored, if not passed as an argument,
            screenshots will not be logged.
        """
        self._playwright = playwright
        self._url = url
        self._headless = headless
        self._max_wait_time = max_wait_time
        self._screenshots_dir_path = screenshots_dir_path
        self._browser = None
        self._context = None
        self._page = None
        self._viz_element = None


    @property
    def playwright(self) -> PlaywrightContextManager:
        return self._playwright


    @property
    def url(self) -> str:
        return self._url


    @property
    def headless(self) -> bool:
        return self._headless


    @property
    def max_wait_time(self) -> int:
        return self._max_wait_time


    @property
    def screenshots_dir_path(self) -> int:
        return self._screenshots_dir_path


    @property
    def browser(self) -> Browser:
        return self._browser


    @property
    def context(self) -> BrowserContext:
        return self._context


    @property
    def page(self) -> Page:
        return self._page


    @property
    def viz_element(self) -> VizElement | None:
        return self._viz_element


    async def setup(self) -> None:
        """
        Set up the Playwright browser and page.
        """
        # Launch the browser and create a new page
        self._browser = await self.playwright.chromium.launch(headless=self.headless)
        self._context = await self.browser.new_context()
        self._page = await self.context.new_page()

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
        executable_cells = await self.collect_executable_cells()

        # Start profiling
        logger.info("Starting profiling...")

        sleep_time = 2
        # Execute each cell and wait for outputs
        for executable_cell in executable_cells:
            await executable_cell.execute()
            # Wait a bit to ensure stability before moving to the next cell
            logger.info(f"Sleeping {sleep_time} seconds to ensure stability...")
            await asyncio.sleep(sleep_time)

        # Log the total execution time for all cells
        total_execution_time = sum(
            executable_cell.execution_time for executable_cell in executable_cells
        )
        logger.info(f"Cells execution times: {total_execution_time}")
        logger.info("Profiling completed.")


    async def detect_viz_element(self) -> None:
        """
        Detect the viz element based on the CSS classes given to the viz app.
        """
        viz_element = await self.page.query_selector(self.VIZ_ELEMENT_SELECTOR)
        if viz_element:
            self._viz_element = VizElement(element=viz_element, profiler=self)
            logger.debug("Viz element detected and assigned")


    async def log_screenshots(self, cell_index: int, screenshots: list[bytes]) -> None:
        """
        Save screenshots of a cell to a determined directory path.
        Parameters
        ----------
        cell_index : int
            The index of the cell.
        screenshots : list[bytes]
            The list of screenshot (in bytes) to save.
        """
        try:
            if self.screenshots_dir_path is None:
                logger.debug("Not logging screenshots")
                return

            # Log screenshots
            logger.debug("Logging screenshots...")

            file_path_name = os_path_join(
                self.screenshots_dir_path,
                f"{perf_counter_ns()}_cell{cell_index}"
            )

            for i, screenshot in enumerate(screenshots):
                # Save first screenshot
                image_file_path_name = f"{file_path_name}_{i}.png"
                image = Image.open(BytesIO(screenshot))
                image.save(image_file_path_name)

            logger.debug("Screenshots logged")

        except Exception as e:
            # In case of an exception: log it and move on (do not block!)
            logger.exception(f"An exception occurred during screenshots logging: {e}")


    async def collect_executable_cells(self) -> list[ExecutableCell]:
        """
        Collect all code cells in the notebook and return them as a list of
        ExecutableCell instances.
        Returns
        -------
        list[ExecutableCell]
            List of ExecutableCell instances representing the code cells in the notebook.
        """
        # Collect all code cells in the notebook
        nb_cells = await self.page.query_selector_all(self.NB_CELLS_SELECTOR)
        # Store cells in an ordered dictionary with their index
        executable_cells = [
            ExecutableCell(cell=cell, index=i, profiler=self) for i, cell in enumerate(nb_cells, 1)
        ]
        logger.info(f"Number of cells in the notebook: {len(executable_cells)}")
        return executable_cells


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
        self._url = url
        self._token = token
        self._kernel_name = kernel_name
        self._nb_input_path = nb_input_path
        self._headers = {
            "Authorization": f"token {self._token}",
            "Content-Type": "application/json",
        }
        self._notebook_url = (
            f"{self._url}/lab/tree/{self._nb_input_path.split('/')[-1]}/"
            f"?token={self._token}"
        )


    @property
    def url(self) -> str:
        return self._url


    @property
    def token(self) -> str:
        return self._token


    @property
    def kernel_name(self) -> str:
        return self._kernel_name


    @property
    def nb_input_path(self) -> str:
        return self._nb_input_path


    @property
    def headers(self) -> dict:
        return self._headers


    @property
    def notebook_url(self) -> str:
        return self._notebook_url


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
        max_wait_time: int, screenshots_dir_path: str | None = None, log_level: str = "INFO"
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
    screenshots_dir_path : str, optional
        Path to the directory to where screenshots will be stored, if not passed as an argument,
        screenshots will not be logged.
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
        f"Screenshots Dir Path: {screenshots_dir_path} -- "
        f"Log Level: {log_level}"
    )

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

    if screenshots_dir_path:
        # Create the directory(ies), if not yet created, in where the screenshots will be saved
        # e.g.: <screenshots_dir_path>/<nb_filename_wo_ext>/<YYYY_MM_DD>/
        screenshots_dir_path = os_path_join(
            screenshots_dir_path,
            splitext(basename(nb_input_path))[0],
            strftime("%Y_%m_%d", gmtime())
        )
        makedirs(screenshots_dir_path, exist_ok=True)

    # Start Playwright and run the profiler
    async with async_playwright() as p:
        profiler = Profiler(
            playwright=p,
            url=jupyter_lab_helper.notebook_url,
            headless=headless,
            max_wait_time=max_wait_time,
            screenshots_dir_path=screenshots_dir_path,
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
        "--screenshots_dir_path",
        help = "Path to the directory to where screenshots will be stored (default: None).",
        required = False,
        type = str,
        default = None,
    )
    parser.add_argument(
        "--log_level",
        help = "Set the logging level (default: INFO).",
        required = False,
        type = str,
        default = "INFO",
        choices = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(profile_notebook(**vars(parser.parse_args())))
