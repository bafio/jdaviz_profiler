#!/usr/bin/env python3
"""
Script to profile notebooks.
"""

import pdb

import argparse
import asyncio
import os
import logging
import time

from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright


logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


async def profile(url, output_path, headless, wait_after_execute):
    """
    Profile the notebook at the specified URL using Playwright.
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
        logger.info("Sleeping 5 seconds to ensure full load...")
        time.sleep(5)  # Wait a bit to ensure the page is fully loaded
        cells = await page.query_selector_all(
            ".jp-WindowedPanel-viewport>.lm-Widget.jp-Cell.jp-CodeCell.jp-Notebook-cell"
        )
        logger.info(f"Number of cells in the notebook: {len(cells)}")

        # Execute each cell and wait for outputs
        for cell_index, cell in enumerate(cells, start=1):
            await cell.focus()  # Focus on the cell
            await page.keyboard.press('Shift+Enter')  # Execute the cell
            logger.info(f"Executing {cell_index} cell")

            start = time.time()
            output_cells = []

            # Wait up to wait_after_execute seconds or until output appears
            while time.time() - start < wait_after_execute:
                output_cells = await cell.query_selector_all(
                    ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"
                )

                await asyncio.sleep(2)  # Check every second

                # If we have at least one output, break and don't wait further
                if len(output_cells):
                    break

            # If no output appeared, log and continue to next cell
            if not len(output_cells):
                logger.info(
                    f"No output appeared for cell {cell_index} after {wait_after_execute} seconds."
                )
                continue

            # filter to only text outputs
            output_cells = await output_cells[0].query_selector_all(
                ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"
            )

            if not len(output_cells):
                logger.info(f"No text output appeared for cell {cell_index}.")
                continue

            output_txt = await output_cells[0].inner_text()

            logger.info(f"Text output for cell {cell_index}: {output_txt}")
            logger.info("Sleeping 5 seconds to ensure stability...")
            time.sleep(5)  # Wait a bit for the next cell to be ready


        logger.info("Profiling completed.")

        await context.close()
        await browser.close()

        return

        # Execute all cells in the notebook
        page.click('data-command="runmenu:run-all"')

        # Wait for all cells to finish executing
        page.wait_for_function(
            """() => {
                const cells = document.querySelectorAll('.jp-Cell');
                return Array.from(cells).every(cell =>
                    cell.classList.contains('jp-mod-executed') ||
                    cell.classList.contains('jp-mod-error')
                );
            }"""
        )

        # End profiling
        page.evaluate("performance.mark('endProfiling')")
        page.evaluate("performance.measure('notebookExecution', 'startProfiling', 'endProfiling')")

        # Retrieve profiling results
        measures = page.evaluate("performance.getEntriesByType('measure')")
        for measure in measures:
            if measure['name'] == 'notebookExecution':
                logger.info(f"Notebook execution time: {measure['duration']} ms")

        # Save profiling results to a file
        output_file = os.path.join(output_path, "profiling_results.txt")
        with open(output_file, "w") as f:
            for measure in measures:
                f.write(f"{measure['name']}: {measure['duration']} ms\n")

        logger.info(f"Profiling results saved to {output_file}")

        context.close()
        browser.close()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description = "Script to profile notebooks."
    )
    parser.add_argument(
        "--url",
        help = "The URL hosting the notebook to profile, including any token and notebook path.",
        required = True,
        type = str,
    )
    parser.add_argument(
        "--output_path",
        help = "Output path directory - if not specified, this defaults to output_<timestamp>",
        required = False,
        type = str,
        default = f"output_{time.strftime('%Y-%m-%dT%H-%M-%S')}"
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
        help = "Time to wait after executing each cell (in seconds, default: 30).",
        required = False,
        type = int,
        default = 30,
    )
    parser.add_argument(
        "--log_level",
        help = "Set the logging level (default: INFO).",
        default = "INFO",
        choices = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )

    args = parser.parse_args()

    # Set up logging
    logger.setLevel(args.log_level.upper())

    logger.info(
        "Starting profiler with "
        f"URL: {args.url} -- "
        f"Output Path: {args.output_path} -- "
        f"Headless: {args.headless} -- "
        f"Wait After Execute: {args.wait_after_execute} -- "
        f"Log Level: {args.log_level}"
    )

    os.makedirs(args.output_path, exist_ok=True)

    asyncio.run(profile(
        url=args.url,
        output_path=args.output_path,
        headless=args.headless,
        wait_after_execute=args.wait_after_execute
    ))
