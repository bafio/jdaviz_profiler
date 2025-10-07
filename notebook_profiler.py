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
import json
import logging
import re
from datetime import timedelta
from io import BytesIO
from os import linesep, makedirs
from os.path import basename, splitext
from os.path import join as os_path_join
from time import gmtime, perf_counter_ns, strftime, time

import nbformat
import psutil
import requests
from chromedriver_py import binary_path
from PIL import Image
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)

KILOBYTE = 1024
MEGABYTE = 1024 * KILOBYTE


class VizElement:
    """Class representing the viz element in a Jupyter notebook."""

    # Seconds to wait during the screenshots taking
    WAIT_TIME_DURING_SCREENSHOTS = 0.5

    def __init__(self, element: WebElement, profiler: "Profiler") -> None:
        """
        Initialize the VizElement with a Selenium WebElement.
        Parameters
        ----------
        element : WebElement
            The Selenium WebElement representing the viz element.
        profiler : Profiler
            The Profiler instance.
        """
        self._element = element
        self._profiler = profiler

    @property
    def element(self) -> WebElement:
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
        screenshot_before = self.element.screenshot_as_png

        # Wait a short period before taking another screenshot
        await asyncio.sleep(self.WAIT_TIME_DURING_SCREENSHOTS)

        # Take another screenshot of the viz element
        screenshot_after = self.element.screenshot_as_png

        # Log screenshots
        await self.profiler.log_screenshots(
            cell_index, [screenshot_before, screenshot_after]
        )

        # Compare the two screenshots
        screenshots_are_the_same = screenshot_before == screenshot_after
        logger.debug(f"screenshots_are_the_same: {screenshots_are_the_same}")
        return screenshots_are_the_same


class ExecutableCell:
    """Class representing an executable cell in a Jupyter notebook."""

    # Seconds to wait after the execution command if no need to
    # collect profiling metrics
    SECONDS_TO_WAIT_IF_SKIP_PROFILING = 2.5

    # Seconds to wait before checking the executed cell outputs
    WAIT_TIME_BEFORE_OUTPUT_CHECK = 0.5

    # Selector for all output cells in a code cell
    OUTPUT_CELLS_SELECTOR = ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"

    # Selector for all text output cells in a code cell
    OUTPUT_CELLS_TEXT_SELECTOR = (
        ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"
    )

    # Regex to identify the cell output containing the `DONE` text output
    OUTPUT_CELL_DONE_REGEX = r"^.*(?P<DONE>DONE).*$"

    def __init__(
        self,
        cell: WebElement,
        index: int,
        skip_profiling: bool,
        wait_for_viz: bool,
        profiler: "Profiler",
    ) -> None:
        """
        Initialize the ExecutableCell with a Selenium WebElement and an optional index.
        Parameters
        ----------
        cell : WebElement
            The Selenium WebElement representing the cell.
        index : int
            The index of the cell.
        skip_profiling : bool
            Mark the ExecutableCell as to skip the collectection or not of
            profiling metrics during its execution.
        wait_for_viz : bool
            Mark the ExecutableCell as to wait if viz is stable
        profiler : Profiler
            The Profiler instance.
        """
        self._cell = cell
        self._index = index
        self._skip_profiling = skip_profiling
        self._wait_for_viz = wait_for_viz
        self._profiler = profiler
        self.execution_time = 0
        self.cpu_usage = 0
        self.memory_usage = 0

    @property
    def cell(self) -> WebElement:
        return self._cell

    @property
    def index(self) -> int:
        return self._index

    @property
    def skip_profiling(self) -> bool:
        return self._skip_profiling

    @property
    def wait_for_viz(self) -> bool:
        return self._wait_for_viz

    @property
    def profiler(self) -> "Profiler":
        return self._profiler

    async def look_for_done_statement(self) -> bool:
        """
        Look for the DONE statement in the output cells of the cell.
        Returns
        -------
        bool
            True if the DONE statement is found, False otherwise.
        """
        output_cells = self.cell.find_elements(
            By.CSS_SELECTOR, self.OUTPUT_CELLS_SELECTOR
        )
        if not output_cells:
            logger.debug(f"Cell {self.index} has no output cells yet, waiting...")
            return False
        for output_cell in output_cells:
            text_output_cells = output_cell.find_elements(
                By.CSS_SELECTOR, self.OUTPUT_CELLS_TEXT_SELECTOR
            )
            logger.debug(f"Found {len(text_output_cells)} text output cells")
            if not text_output_cells:
                continue
            output_txt = linesep.join(
                [text_output_cell.text for text_output_cell in text_output_cells]
            )
            match = re.search(self.OUTPUT_CELL_DONE_REGEX, output_txt, re.MULTILINE)
            if match and match.group("DONE"):
                logger.info(f"Cell {self.index} DONE statement found!")
                return True
        return False

    async def execute(self) -> None:
        try:
            logger.info(f"Executing cell {self.index}")
            # Click on the cell
            self.cell.click()
            # Execute the cell
            self.cell.send_keys(Keys.SHIFT, Keys.ENTER)

            # Initialize variables to track the viz element and elapsed time
            viz_is_stable = False
            time_elapsed = 0
            cpu_usage = []
            memory_usage = []
            timer = time()

            while True:
                if not self.skip_profiling:
                    # Capture CPU usage
                    cpu_usage.append(
                        psutil.cpu_percent(interval=self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
                    )
                    # Capture memory usage
                    memory_usage.append(psutil.virtual_memory().percent)

                # Wait a bit before checking again
                await asyncio.sleep(self.WAIT_TIME_BEFORE_OUTPUT_CHECK)

                # Check if the DONE statement
                done_found = await self.look_for_done_statement()
                if not done_found:
                    logger.debug(f"Cell {self.index} DONE statement not found yet...")
                    continue

                logger.debug(f"Cell {self.index} DONE statement found, moving on...")

                if not self.wait_for_viz:
                    logger.debug(
                        f"Cell {self.index} is not tagged as to wait for viz changes, "
                        "moving on..."
                    )
                    # save time elapsed
                    time_elapsed = time() - timer
                    break

                logger.debug(f"Cell {self.index} is tagged as to wait for viz changes.")
                if self.profiler.viz_element:
                    # If we have the viz element, check if it's stable
                    logger.debug(
                        "We already have the viz element, checking if it's stable..."
                    )
                    viz_is_stable = await self.profiler.viz_element.is_stable(
                        self.index
                    )
                else:
                    # Look for the viz element in the page
                    logger.debug("Looking for the viz element in the page...")
                    await self.profiler.detect_viz_element()

                if viz_is_stable:
                    logger.debug(
                        f"Cell {self.index} viz element is stable, moving on..."
                    )
                    # save time elapsed
                    time_elapsed = time() - timer
                    break

            if self.skip_profiling:
                self.execution_time = 0
                self.cpu_usage = 0
                self.memory_usage = 0
            else:
                self.execution_time = time_elapsed
                cpu_usage.append(
                    psutil.cpu_percent(interval=self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
                )
                self.cpu_usage = sum(cpu_usage) / len(cpu_usage) if cpu_usage else 0
                memory_usage.append(psutil.virtual_memory().percent)
                self.memory_usage = (
                    sum(memory_usage) / len(memory_usage) if memory_usage else 0
                )

            # Log the time elapsed for the cell execution
            logger.info(
                f"Cell {self.index} completed in {self.execution_time:.2f} seconds. "
                f"Average CPU usage: {self.cpu_usage:.2f}%. "
                f"Average Memory usage: {self.memory_usage:.2f}%"
            )

        except Exception as e:
            logger.exception(
                f"An error occurred while executing cell {self.index}: {e}"
            )


class Profiler:
    """Class to profile a Jupyter notebook using Selenium."""

    # The width and height to set for the browser viewport to make the page really tall
    # to avoid scrollbars and scrolling issues
    VIEWPORT_SIZE = {"width": 1600, "height": 20000}

    # Window size options
    WINDOW_SIZE_OPTION = (
        f"--window-size={VIEWPORT_SIZE['width']},{VIEWPORT_SIZE['height']}"
    )

    # CSS style to disable the pulsing animation that can interfere
    # with screenshots taking
    PAGE_STYLE_TAG_CONTENT = ".viewer-label.pulse {animation: none !important;}"

    # Selector for the notebook element
    NB_SELECTOR = ".jp-Notebook"

    # Selector for all code cells in the notebook
    NB_CELLS_SELECTOR = (
        ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"
    )

    # The value of the cell tag marked as to skip metrics collections during profiling
    SKIP_PROFILING_CELL_TAG = "skip_profiling"

    # The value of the cell tag marked as to wait for the viz
    WAIT_FOR_VIZ_CELL_TAG = "wait_for_viz"

    # The value of the cell tag holding the notebook parameters
    PARAMETERS_CELL_TAG = "parameters"

    # The parameter name holding the ui_network_throttling value
    UI_NETWORK_THROTTLING_PARAM = "ui_network_throttling"

    # The regex to find the ui_network_throttling value
    UI_NETWORK_THROTTLING_REGEX = (
        rf".*{UI_NETWORK_THROTTLING_PARAM}\s*\=\s*(?P<value>[-+]?\d+).*"
    )

    # Selector for the jdaviz app viz element
    VIZ_ELEMENT_SELECTOR = ".jdaviz.imviz"

    def __init__(
        self,
        url: str,
        headless: str,
        max_wait_time: int,
        nb_input_path: str,
        screenshots_dir_path: str = None,
    ) -> None:
        """
        Initialize the Profiler with URL, headless mode, and wait time.
        Parameters
        ----------
        url : str
            The URL of the notebook to profile.
        headless : bool
            Whether to run in headless mode.
        max_wait_time : int
            Time to wait after executing each cell (in seconds).
        nb_input_path : str
            Path to the input notebook to be profiled.
        screenshots_dir_path : str, optional
            Path to the directory to where screenshots will be stored, if not passed as
            an argument, screenshots will not be logged.
        """
        self._url = url
        self._headless = headless
        self._max_wait_time = max_wait_time
        self._nb_input_path = nb_input_path
        self._screenshots_dir_path = screenshots_dir_path
        self._driver = None
        self._viz_element = None
        self.ui_network_throttling_value = None
        self.skip_profiling_cell_indexes = frozenset()
        self.wait_for_viz_cell_indexes = frozenset()

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
    def nb_input_path(self) -> str:
        return self._nb_input_path

    @property
    def screenshots_dir_path(self) -> int:
        return self._screenshots_dir_path

    @property
    def driver(self) -> WebDriver:
        return self._driver

    @property
    def viz_element(self) -> VizElement | None:
        return self._viz_element

    async def setup(self) -> None:
        """
        Set up the Selenium browser and page.
        """
        # Inspect the notebook file to find "skip_profiling" cells and
        # "network_bandwith" value
        await self.inspect_notebook()

        options = Options()
        options.add_argument(self.WINDOW_SIZE_OPTION)

        if self.headless:
            options.add_argument("--headless=new")

        # Launch the browser and create a new page
        self._driver = Chrome(
            options=options, service=ChromeService(executable_path=binary_path)
        )

        # Navigate to the notebook URL
        logger.info(f"Navigating to {self.url}")
        self.driver.get(self.url)

        # Wait for the notebook to load
        WebDriverWait(self.driver, 10).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, self.NB_SELECTOR))
        )
        logger.debug("Notebook loaded")

        # If ui_network_throttling_value is not None, set up the network throttling
        if self.ui_network_throttling_value is not None:
            self.driver.set_network_conditions(
                offline=False,
                latency=0,
                download_throughput=self.ui_network_throttling_value,
                upload_throughput=-1,  # -1 means no throttling
            )

        # Apply custom viewport size
        self.driver.set_window_size(*self.VIEWPORT_SIZE.values())
        logger.debug("Page viewport set")

        # Apply custom CSS styles
        self.driver.execute_script(
            "const style = document.createElement('style'); "
            f"style.innerHTML = `{self.PAGE_STYLE_TAG_CONTENT}`; "
            "document.head.appendChild(style);"
        )
        logger.debug("Page style added")

    async def run(self) -> None:
        """
        Run the profiling process.
        """
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
        logger.info(
            "All the cells in the notebook have been executed. "
            f"The total execution time is: {timedelta(seconds=total_execution_time)}"
        )
        logger.info("Profiling completed.")

    async def detect_viz_element(self) -> None:
        """
        Detect the viz element based on the CSS classes given to the viz app.
        """
        viz_element = self.driver.find_element(
            By.CSS_SELECTOR, self.VIZ_ELEMENT_SELECTOR
        )
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
                self.screenshots_dir_path, f"{perf_counter_ns()}_cell{cell_index}"
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
            List of ExecutableCell instances representing the code cells
            in the notebook.
        """
        # Collect all code cells in the notebook
        nb_cells = self.driver.find_elements(By.CSS_SELECTOR, self.NB_CELLS_SELECTOR)

        # Store cells in an ordered dictionary with their index
        executable_cells = [
            ExecutableCell(
                cell=cell,
                index=i,
                skip_profiling=i in self.skip_profiling_cell_indexes,
                wait_for_viz=i in self.wait_for_viz_cell_indexes,
                profiler=self,
            )
            for i, cell in enumerate(nb_cells, 1)
        ]
        logger.info(f"Number of cells in the notebook: {len(executable_cells)}")
        return executable_cells

    async def inspect_notebook(self) -> None:
        """
        Inspect the notebook file to find "skip_profiling" cells and
        "network_bandwith" value.
        """
        nb = nbformat.read(self.nb_input_path, nbformat.NO_CONVERT)
        await self.collect_cells_metadata(nb)
        await self.get_ui_network_throttling_value(nb)

    async def collect_cells_metadata(self, notebook: nbformat.NotebookNode) -> None:
        """
        Collect the indexes of cells marked with specific tags, such as:
        - SKIP_PROFILING_CELL_TAG
        - WAIT_FOR_VIZ_CELL_TAG
        Parameters
        ----------
        notebook : nbformat.NotebookNode
            The notebook to read from.
        """
        skip_profiling_cell_indexes = []
        wait_for_viz_cell_indexes = []
        for cell_index, cell in enumerate(notebook.cells, 1):
            # Get the nb cell tags
            tags = cell.metadata.get("tags", [])
            if self.SKIP_PROFILING_CELL_TAG in tags:
                skip_profiling_cell_indexes.append(cell_index)
            if self.WAIT_FOR_VIZ_CELL_TAG in tags:
                wait_for_viz_cell_indexes.append(cell_index)

        self.skip_profiling_cell_indexes = frozenset(skip_profiling_cell_indexes)
        logger.debug(
            "Profiling metrics for the following cells "
            f"{tuple(self.skip_profiling_cell_indexes)} will not be collected."
        )
        self.wait_for_viz_cell_indexes = frozenset(wait_for_viz_cell_indexes)
        logger.debug(
            "The following cells "
            f"{tuple(self.wait_for_viz_cell_indexes)} will only wait for "
            "viz changes (if viz is set)."
        )

    async def get_ui_network_throttling_value(
        self, notebook: nbformat.NotebookNode
    ) -> None:
        """
        Collect the ui network throttling value from the notebook if set in the
        cell tagged as parameters.
        Parameters
        ----------
        notebook : nbformat.NotebookNode
            The notebook to read from.
        """
        for cell in notebook.cells:
            # Get the nb cell tagged with the specified cell_tag
            tags = cell.metadata.get("tags", [])
            if self.PARAMETERS_CELL_TAG in tags:
                cell_source = cell.source or ""
                match = re.search(self.UI_NETWORK_THROTTLING_REGEX, cell_source)
                if match and match.group("value"):
                    value = int(match.group("value"))
                    if value > 0:
                        self.ui_network_throttling_value = value * MEGABYTE
                # Once a cell tagged as parameters has been found, there is no need
                # to keep looking
                return

    async def close(self) -> None:
        """
        Close the Selenium driver.
        """
        self.driver.quit()
        logger.debug("Driver closed")


class JupyterLabHelper:
    """Helper class to interact with JupyterLab."""

    def __init__(
        self, url: str, token: str, kernel_name: str, nb_input_path: str
    ) -> None:
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
        Clear all active sessions (notebooks, consoles, terminals) in the
        JupyterLab instance.
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
                session_id = session["id"]
                shutdown_url = f"{self.url}/api/sessions/{session_id}"
                shutdown_response = requests.delete(shutdown_url, headers=self.headers)
                shutdown_response.raise_for_status()

                # Print a status message based on the session type
                if "kernel" in session and session["kernel"]:
                    logger.info(
                        "Shut down notebook/console session: "
                        f"{session['path']} (ID: {session_id})"
                    )
                elif "terminal" in session:
                    logger.info(
                        f"Shut down terminal session: {session['name']} "
                        f"(ID: {session_id})"
                    )
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
                if kernel["name"] == self.kernel_name:
                    kernel_id = kernel["id"]
                    break

            if not kernel_id:
                logger.warning(
                    f"No active kernel found for kernel name: {self.kernel_name}."
                )
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
            notebook_path = self.nb_input_path.split("/")[
                -1
            ]  # Extract filename from path
            upload_url = f"{self.url}/api/contents/{notebook_path}"
            logger.info(f"Uploading notebook to {upload_url}")

            with open(self.nb_input_path, "r", encoding="utf-8") as nb_file:
                notebook_content = json.load(nb_file)

            payload = {
                "content": notebook_content,
                "type": "notebook",
                "format": "json",
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
            notebook_path = self.nb_input_path.split("/")[
                -1
            ]  # Extract filename from path
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
    url: str,
    token: str,
    kernel_name: str,
    nb_input_path: str,
    headless: bool,
    max_wait_time: int,
    screenshots_dir_path: str | None = None,
    log_level: str = "INFO",
) -> None:
    """
    Profile the notebook at the specified URL using Selenium.
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
        Path to the directory to where screenshots will be stored, if not passed as
        an argument, screenshots will not be logged.
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
        # Create the directory(ies), if not yet created, in where the screenshots
        # will be saved. e.g.: <screenshots_dir_path>/<nb_filename_wo_ext>/<YYYY_MM_DD>/
        screenshots_dir_path = os_path_join(
            screenshots_dir_path,
            splitext(basename(nb_input_path))[0],
            strftime("%Y_%m_%d", gmtime()),
        )
        makedirs(screenshots_dir_path, exist_ok=True)

    # Start Selenium and run the profiler
    profiler = Profiler(
        url=jupyter_lab_helper.notebook_url,
        headless=headless,
        max_wait_time=max_wait_time,
        nb_input_path=nb_input_path,
        screenshots_dir_path=screenshots_dir_path,
    )
    try:
        await profiler.setup()
        await profiler.run()
    finally:
        await profiler.close()

    # Clean up by deleting the uploaded notebook
    await jupyter_lab_helper.delete_notebook()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
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
        "--max_wait_time",
        help="Max time to wait after executing each cell (in seconds, default: 10).",
        required=False,
        type=int,
        default=10,
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
        "--log_level",
        help="Set the logging level (default: INFO).",
        required=False,
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(profile_notebook(**vars(parser.parse_args())))
