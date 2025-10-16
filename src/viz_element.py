import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from selenium.webdriver.remote.webelement import WebElement

if TYPE_CHECKING:
    from .profiler import Profiler  # Avoid circular import

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass(eq=False, frozen=True)
class VizElement:
    """Class representing the viz element in a Jupyter notebook."""

    element: WebElement
    profiler: "Profiler"

    # Seconds to wait during the screenshots taking
    WAIT_TIME_DURING_SCREENSHOTS: ClassVar[float] = 0.5

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
        screenshot_before: bytes = self.element.screenshot_as_png

        # Wait a short period before taking another screenshot
        await asyncio.sleep(self.WAIT_TIME_DURING_SCREENSHOTS)

        # Take another screenshot of the viz element
        screenshot_after: bytes = self.element.screenshot_as_png

        # Log screenshots
        await self.profiler.log_screenshots(
            cell_index, [screenshot_before, screenshot_after]
        )

        # Compare the two screenshots
        screenshots_are_the_same: bool = screenshot_before == screenshot_after
        logger.debug(f"screenshots_are_the_same: {screenshots_are_the_same}")
        return screenshots_are_the_same
