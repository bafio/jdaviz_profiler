import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from selenium.webdriver.remote.webelement import WebElement

from src.utils import explicit_wait, get_logger

# Avoid circular import
if TYPE_CHECKING:
    from .profiler import Profiler

# Initialize logger
logger: logging.Logger = get_logger()


@dataclass(frozen=True, eq=False)
class VizElement:
    """Class representing the viz element in a Jupyter notebook."""

    element: WebElement
    profiler: "Profiler"

    # Seconds to wait during the screenshots taking
    WAIT_TIME_DURING_SCREENSHOTS: ClassVar[float] = 0.5

    def is_stable(self, cell_index: int) -> bool:
        """
        Check if the viz element is stable (i.e., not changing).
        Returns
        -------
        bool
            True if the viz element is stable, False otherwise.
        """
        if self.element is None:
            logger.debug("Viz element element is None, cannot be stable.")
            return False

        # Take a screenshot of the viz element
        screenshot_before: bytes = self.element.screenshot_as_png

        # Wait a short period before taking another screenshot
        explicit_wait(self.WAIT_TIME_DURING_SCREENSHOTS)

        # Take another screenshot of the viz element
        screenshot_after: bytes = self.element.screenshot_as_png

        # Log screenshots
        self.profiler.log_screenshots(cell_index, (screenshot_before, screenshot_after))

        # Compare the two screenshots
        screenshots_are_the_same: bool = screenshot_before == screenshot_after
        logger.debug(f"screenshots_are_the_same: {screenshots_are_the_same}.")
        return screenshots_are_the_same
