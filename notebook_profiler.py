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
import time

from playwright.async_api import async_playwright, ElementHandle, Page


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


async def clear_jupyterlab_sessions(base_url: str, headers: dict) -> None:
    """
    Clear all active sessions (notebooks, consoles, terminals) in the JupyterLab instance.
    Parameters
    ----------
    base_url : str
        The base URL of the JupyterLab instance.
    headers : dict
        The headers to use for authentication (e.g., including the token).
    Raises
    ------
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    try:
        # Get a list of all running sessions
        sessions_url = f"{base_url}/api/sessions"
        response = requests.get(sessions_url, headers=headers)
        response.raise_for_status()
        sessions = response.json()

        if not sessions:
            logger.info("No active sessions found.")
            return

        logger.info(f"Found {len(sessions)} active sessions. Shutting them down...")

        # Shut down each session
        for session in sessions:
            session_id = session['id']
            shutdown_url = f"{base_url}/api/sessions/{session_id}"
            shutdown_response = requests.delete(shutdown_url, headers=headers)
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


async def restart_kernel(base_url: str, headers: dict, kernel_name: str) -> None:
    """
    Restart the kernel for a given kernel name.
    Parameters
    ----------
    base_url : str
        The base URL of the JupyterLab instance.
    headers : dict
        The headers to use for authentication (e.g., including the token).
    kernel_name : str
        The name of the kernel to restart (e.g., 'python3', 'roman-cal').
    Raises
    ------
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    try:
        # Get the list of all kernels
        kernels_url = f"{base_url}/api/kernels"
        response = requests.get(kernels_url, headers=headers)
        response.raise_for_status()
        kernels = response.json()

        # Find the kernel ID for the given kernel name
        kernel_id = None
        for kernel in kernels:
            if kernel['name'] == kernel_name:
                kernel_id = kernel['id']
                break

        if not kernel_id:
            logger.warning(f"No active kernel found for kernel name: {kernel_name}.")
            return

        # Restart the kernel
        restart_url = f"{base_url}/api/kernels/{kernel_id}/restart"
        restart_response = requests.post(restart_url, headers=headers)
        restart_response.raise_for_status()

        logger.info(f"Kernel {kernel_name} restarted successfully.")

    except requests.exceptions.RequestException as e:
        logger.exception(f"Error communicating with JupyterLab server: {e}")
        raise e
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        raise e


async def upload_notebook(base_url: str, headers: dict, nb_input_path: str) -> None:
    """
    Upload the notebook to the JupyterLab instance.
    Parameters
    ----------
    base_url : str
        The base URL of the JupyterLab instance.
    headers : dict
        The headers to use for authentication (e.g., including the token).
    nb_input_path : str
        The path to the notebook file to be uploaded.
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
        notebook_path = nb_input_path.split('/')[-1]  # Extract filename from path
        upload_url = f"{base_url}/api/contents/{notebook_path}"
        logger.info(f"Uploading notebook to {upload_url}")

        with open(nb_input_path, 'r', encoding='utf-8') as nb_file:
            notebook_content = json.load(nb_file)

        payload = {
            "content": notebook_content,
            "type": "notebook",
            "format": "json"
        }

        response = requests.put(upload_url, headers=headers, json=payload)
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


async def delete_notebook(base_url: str, headers: dict, nb_input_path: str) -> None:
    """
    Delete the notebook from the JupyterLab instance.
    Parameters
    ----------
    base_url : str
        The base URL of the JupyterLab instance.
    headers : dict
        The headers to use for authentication (e.g., including the token).
    nb_input_path : str
        The path to the notebook file to be deleted.
    Raises
    ------
    requests.exceptions.RequestException
        If there is an error communicating with the JupyterLab server.
    Exception
        For any other unexpected errors.
    """
    try:
        notebook_path = nb_input_path.split('/')[-1]  # Extract filename from path
        delete_url = f"{base_url}/api/contents/{notebook_path}"
        logger.info(f"Deleting notebook at {delete_url}")

        response = requests.delete(delete_url, headers=headers)
        response.raise_for_status()

        logger.info(f"Notebook deleted successfully from {delete_url}")

    except requests.exceptions.RequestException as e:
        logger.exception(f"Error deleting notebook: {e}")
        raise e
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
        raise e


async def execute_cell(
        page: Page, cell: ElementHandle, cell_index: int, wait_after_execute: int
) -> None:
    """
    Execute a single cell and wait for its output.
    Parameters
    ----------
    page : Page
        The Playwright page object.
    cell : ElementHandle
        The cell element to be executed.
    cell_index : int
        The index of the cell (for logging purposes).
    wait_after_execute : int
        Time to wait after executing the cell (in seconds).
    Raises
    ------
    Exception
        For any unexpected errors during cell execution.
    """
    try:
        await cell.focus()  # Focus on the cell
        await page.keyboard.press('Shift+Enter')  # Execute the cell
        logger.info(f"Executing cell {cell_index}")

        start = time.time()
        output_cells = []

        sleep_time = 1
        # Wait up to wait_after_execute seconds or until output appears
        while time.time() - start < wait_after_execute:
            output_cells = await cell.query_selector_all(
                ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"
            )

            # wait before checking if output appeared
            await asyncio.sleep(sleep_time)

            # If we have at least one output, break and don't wait further
            if len(output_cells):
                break

        # If no output appeared, log and return
        if not len(output_cells):
            logger.info(
                f"No output appeared for cell {cell_index} after {wait_after_execute} seconds."
            )
            return

        # filter to only text outputs
        output_cells = await output_cells[0].query_selector_all(
            ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"
        )

        if not len(output_cells):
            logger.info(f"No text output appeared for cell {cell_index}.")
            return

        output_txt = await output_cells[0].inner_text()

        logger.info(f"Text output for cell {cell_index}: {output_txt}")

    except Exception as e:
        logger.exception(f"An error occurred while executing cell {cell_index}: {e}")


async def _profile_notebook(url: str, headless: str, wait_after_execute: int) -> None:
    """
    Profile the notebook at the specified URL using Playwright.
    Parameters
    ----------
    url : str
        The URL of the notebook to be profiled.
    headless : bool
        Whether to run in headless mode.
    wait_after_execute : int
        Time to wait after executing each cell (in seconds).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()
        page = await context.new_page()

        logger.info(f"Navigating to {url}")
        await page.goto(url)

        # Wait for the notebook to load
        await page.wait_for_selector(".jp-Notebook")

        # Start profiling
        logger.info("Starting profiling...")
        sleep_time = 5
        logger.info(f"Sleeping {sleep_time} seconds to ensure full load...")
        await asyncio.sleep(sleep_time)  # Wait a bit to ensure the page is fully loaded
        cells = await page.query_selector_all(
            ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"
        )
        logger.info(f"Number of cells in the notebook: {len(cells)}")

        sleep_time = 2
        # Execute each cell and wait for outputs
        for cell_index, cell in enumerate(cells, start=1):
            await execute_cell(page, cell, cell_index, wait_after_execute)

            logger.info(f"Sleeping {sleep_time} seconds to ensure stability...")
            await asyncio.sleep(sleep_time)  # Wait a bit for the next cell to be ready

        logger.info("Profiling completed.")

        await context.close()
        await browser.close()


async def profile_notebook(
        url: str, token: str, kernel_name: str, nb_input_path: str, headless: bool,
        wait_after_execute: int, log_level: str = "INFO"
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
    wait_after_execute : int
        Time to wait after executing each cell (in seconds).
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
        f"Wait After Execute: {wait_after_execute} -- "
        f"Log Level: {log_level}"
    )

    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
    }

    await clear_jupyterlab_sessions(url, headers)
    await restart_kernel(url, headers, kernel_name)
    await upload_notebook(url, headers, nb_input_path)

    notebook_url = f"{url}/lab/tree/{nb_input_path.split('/')[-1]}/?token={token}"

    await _profile_notebook(
        url=notebook_url,
        headless=headless,
        wait_after_execute=wait_after_execute
    )

    await delete_notebook(url, headers, nb_input_path)


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
        "--wait_after_execute",
        help = "Time to wait after executing each cell (in seconds, default: 5).",
        required = False,
        type = int,
        default = 5,
    )
    parser.add_argument(
        "--log_level",
        help = "Set the logging level (default: INFO).",
        default = "INFO",
        choices = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    asyncio.run(profile_notebook(**vars(parser.parse_args())))
