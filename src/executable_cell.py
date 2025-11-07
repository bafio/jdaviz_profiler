import logging
import re
import warnings
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from os import linesep
from typing import TYPE_CHECKING, Any, ClassVar

import psutil
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from tqdm import TqdmWarning, tqdm

from src.metrics import CellMetrics
from src.utils import CellExecutionStatus, elapsed_time, explicit_wait, get_logger

# Avoid circular import
if TYPE_CHECKING:
    from src.profiler import Profiler

# Initialize logger
logger: logging.Logger = get_logger()
# This is to suppress "TqdmWarning: clamping frac to range [0, 1]" warnings
warnings.filterwarnings("ignore", category=TqdmWarning)


@dataclass(eq=False)
class ExecutableCell:
    """Class representing an executable cell in a Jupyter notebook."""

    cell: WebElement
    index: int
    max_wait_time: int
    skip_profiling: bool
    wait_for_viz: bool
    profiler: "Profiler"
    execution_start_time: float = 0
    done_found: bool = False
    metrics: CellMetrics = field(default_factory=CellMetrics, repr=False, init=False)

    # Seconds to wait after the execution command if no need to
    # collect profiling metrics
    SECONDS_TO_WAIT_IF_SKIP_PROFILING: ClassVar[float] = 2.5

    # Seconds to wait before checking the executed cell outputs
    WAIT_TIME_BEFORE_OUTPUT_CHECK: ClassVar[float] = 0.5

    # Selector for all output cells in a code cell
    OUTPUT_CELLS_SELECTOR: ClassVar[str] = ".lm-Widget.lm-Panel.jp-Cell-outputWrapper"

    # Selector for all text output cells in a code cell
    OUTPUT_CELLS_TEXT_SELECTOR: ClassVar[str] = (
        ".lm-Widget.jp-RenderedText.jp-mod-trusted.jp-OutputArea-output"
    )

    # Regex to identify the cell output containing the `DONE` text output
    OUTPUT_CELL_DONE_REGEX: ClassVar[str] = r"^.*(?P<DONE>DONE).*$"

    def __post_init__(self):
        """Post-initialization to set the cell index in performance metrics."""
        self.metrics.cell_index = self.index

    def execute(self) -> None:
        """
        Execute the cell and collect profiling metrics.
        Raises
        ------
        Exception
            If the kernel PID cannot be retrieved before execution.
        """
        logger.info(f"Start execution of cell {self.index}.")

        # Set kernel PID at the beginning of execution
        kernel_pid: int | None = self.profiler.get_current_kernel_pid()
        if kernel_pid is None:
            raise Exception(
                f"Cannot get kernel PID before executing cell {self.index}."
            )

        # Set up the progress bar for cell execution
        progress_bar: tqdm = tqdm(
            total=self.max_wait_time,
            desc=f"Cell {self.index} Timeout Progress",
            leave=False,
            position=0,
        )

        # Set execution start time
        self.execution_start_time: float = elapsed_time()
        # Click on the cell
        self.cell.click()
        # Execute the cell
        self.cell.send_keys(Keys.SHIFT, Keys.ENTER)

        # Set initial execution status to IN_PROGRESS
        self.metrics.execution_status = CellExecutionStatus.IN_PROGRESS

        # Used to skip the first metrics capture
        first_iter: bool = True
        while self.metrics.execution_status.is_not_final:
            # Capture metrics after the first iteration
            first_iter = not first_iter and self.capture_metrics()  # type: ignore[func-returns-value]
            # Check execution status
            self.check_execution_status(kernel_pid, progress_bar)

        # Finalize the progress bar
        self.finalize_progress_bar(progress_bar)

        # Capture metrics one last time after loop exit
        self.capture_metrics()

        # Compute performance metrics
        self.metrics.compute()

        # Log the performance metrics
        logger.info(str(self.metrics))

    def check_execution_status(self, kernel_pid: int, progress_bar: tqdm) -> None:
        """
        Check the execution status of the cell.
        Parameters
        ----------
        kernel_pid : int
            The PID of the kernel at the start of execution.
        progress_bar : tqdm
            The progress bar to update.
        """
        # Mark the beginning of a loop iteration (for progress bar updates)
        while_elapsed_time: float = elapsed_time()

        # Check for timeout, if time has expired, we're done
        if (et := elapsed_time(self.execution_start_time)) > self.max_wait_time:
            self.metrics.execution_status = CellExecutionStatus.TIMED_OUT
            logger.warning(f"Cell {self.index} execution stopped after {et} seconds.")
            return

        # Check if the kernel has restarted, if yes, we're done
        if kernel_pid != self.profiler.get_current_kernel_pid():
            self.metrics.execution_status = CellExecutionStatus.FAILED
            logger.warning(
                f"Cell {self.index} execution has been interrupted due to a "
                "kernel restart."
            )
            return

        # Wait a bit before checking
        explicit_wait(self.WAIT_TIME_BEFORE_OUTPUT_CHECK)

        # Update progress bar
        progress_bar.update(round(elapsed_time(while_elapsed_time)))
        while_elapsed_time = elapsed_time()

        # Check if the DONE statement has been found, if not try to find it
        if not self.done_found:
            logger.debug(f"Cell {self.index} DONE statement not found yet.")
            self.find_done_statement()
            return

        # If we don't need to wait for viz changes, we are done
        if not self.wait_for_viz:
            logger.debug(f"Cell {self.index} is not waiting for viz changes.")
            self.metrics.execution_status = CellExecutionStatus.COMPLETED
            return

        logger.debug(f"Cell {self.index} has to wait for viz changes.")

        # Check if the viz element is stable
        viz_is_stable: bool = False
        if self.profiler.viz_element:
            # If we have the viz element, check if it's stable
            logger.debug("We already have the viz element, checking if it's stable.")
            viz_is_stable = self.profiler.viz_element.is_stable(self.index)
        else:
            # Look for the viz element in the page
            logger.debug("Looking for the viz element in the page...")
            self.profiler.detect_viz_element()

        # Update progress bar
        progress_bar.update(round(elapsed_time(while_elapsed_time)))

        # Loop exit check: if the viz is stable, we are done
        if viz_is_stable:
            self.metrics.execution_status = CellExecutionStatus.COMPLETED
            logger.debug(f"Cell {self.index} viz element is stable.")

    @staticmethod
    def finalize_progress_bar(progress_bar: tqdm) -> None:
        """
        Finalize the progress bar for cell execution.
        Parameters
        ----------
        progress_bar : tqdm
            The progress bar to finalize.
        """
        # Complete the progress bar smoothly
        steps: int = 10
        step: float = (progress_bar.total - progress_bar.n) / steps
        for _ in range(steps):
            explicit_wait(0.05)
            progress_bar.update(step)
        progress_bar.close()

    def capture_metrics(self) -> None:
        """Capture profiling metrics for the cell execution."""
        # Skip metrics capture if profiling is skipped or
        # if execution has already finished and is failed
        if (
            self.skip_profiling
            or self.metrics.execution_status == CellExecutionStatus.FAILED
        ):
            return

        # Save time elapsed
        self.metrics.total_execution_time = elapsed_time(self.execution_start_time)

        # Capture client CPU usage
        self.metrics.client_cpu_list.append(
            psutil.cpu_percent(interval=self.WAIT_TIME_BEFORE_OUTPUT_CHECK)
        )

        # Capture client memory usage
        self.metrics.client_memory_list.append(psutil.virtual_memory().percent)

        # Get kernel usage metrics only if present
        kernel_usage: dict[str, Any] = self.profiler.get_kernel_usage()
        if "kernel_cpu" in kernel_usage and "host_virtual_memory" in kernel_usage:
            # Capture kernel CPU usage
            self.metrics.kernel_cpu_list.append(kernel_usage["kernel_cpu"])
            # Capture kernel memory usage
            self.metrics.kernel_memory_list.append(
                kernel_usage["host_virtual_memory"]["percent"]
            )
        else:
            logger.warning(
                f"Kernel usage metrics not available for cell {self.index}, "
                "skipping kernel metrics capture."
            )

        # Capture client data received from the profiler only when
        # execution is not in progress
        if self.metrics.execution_status.is_final:
            timestamp_end: datetime = datetime.now()
            timestamp_start: datetime = timestamp_end - timedelta(
                seconds=self.metrics.total_execution_time
            )
            self.metrics.client_total_data_received = (
                self.profiler.get_client_data_received(timestamp_start, timestamp_end)
            )
        logger.debug(f"Cell {self.index} metrics captured.")

    def find_done_statement(self) -> None:
        """Look for the DONE statement in the output cells of the executed cell."""
        output_cells: list[WebElement] = self.cell.find_elements(
            By.CSS_SELECTOR, self.OUTPUT_CELLS_SELECTOR
        )
        if not output_cells:
            logger.debug(f"Cell {self.index} has no output cells yet, waiting...")
            return
        for output_cell in output_cells:
            text_output_cells: list[WebElement] = output_cell.find_elements(
                By.CSS_SELECTOR, self.OUTPUT_CELLS_TEXT_SELECTOR
            )
            logger.debug(f"Found {len(text_output_cells)} text output cells.")
            if not text_output_cells:
                continue
            output_txt: str = linesep.join(
                [text_output_cell.text for text_output_cell in text_output_cells]
            )
            match: re.Match | None = re.search(
                self.OUTPUT_CELL_DONE_REGEX, output_txt, re.MULTILINE
            )
            if match and match.group("DONE"):
                logger.info(f"Cell {self.index} DONE statement found.")
                self.done_found = True
                return
