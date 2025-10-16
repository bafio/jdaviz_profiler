import logging
from dataclasses import dataclass, field
from os import linesep
from typing import ClassVar

from nbformat import NO_CONVERT, NotebookNode
from nbformat import read as nb_read
from nbformat import write as nb_write

logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass(eq=False)
class NotebookGenerator:
    """
    A class to generate Jupyter notebooks by injecting parameters into a
    template notebook.
    Attributes
    ----------
    template_path : str
        Path to the template notebook file.
    output_path : str
        Path to the output notebook file.
    parameters_values : dict
        Dictionary containing parameter names and their values.
    notebook : NotebookNode
        The notebook object representing the template notebook.
    """

    template_path: str
    output_path: str
    parameters_values: dict
    notebook: NotebookNode = field(init=False, repr=False)

    PARAMS_CELL_TAG: ClassVar[str] = "parameters"
    DONE_STATEMENT: ClassVar[str] = 'print("DONE")'

    def __post_init__(self):
        """
        Load the template notebook after initialization.
        """
        self.notebook = nb_read(self.template_path, NO_CONVERT)

    async def clear_notebook_outputs(self) -> None:
        """
        Clear the outputs of all cells in a notebook.
        """
        for cell in self.notebook.cells:
            if cell.cell_type == "code":
                cell.outputs: list[NotebookNode] = []
                cell.execution_count: int | None = None

    async def inject_key_value_data(self) -> None:
        """
        Inject key-value data in the cell tagged as parameters in the notebook.
        Raises
        ------
        ValueError
            If no cell with the specified tag is found in the notebook.
            If the cell is found with no content in the notebook.
        """
        cell_source: str = ""
        cell_found: bool = False

        # Modify the notebook with the provided data
        for cell in self.notebook.cells:
            # Get the nb cell tagged with the specified cell_tag
            tags: list[str] = cell.metadata.get("tags", [])
            if self.PARAMS_CELL_TAG in tags:
                cell_found = True
                cell_source = cell.source
                if not cell_source:
                    msg: str = "Cell found with no content in the notebook."
                    logger.error(msg)
                    raise ValueError(msg)
                cell.source = cell_source.format(**self.parameters_values)
                break

        if not cell_found:
            msg: str = (
                f"No cell with '{self.PARAMS_CELL_TAG}' tag found in the notebook."
            )
            logger.error(msg)
            raise ValueError(msg)

    async def inject_done_statement(self) -> None:
        """
        Inject a `print("DONE")` statement at the end of code cells in the notebook.
        """
        # Modify the template.ipynb with the provided data
        for cell in self.notebook.cells:
            # Skip non code type cells
            if cell.cell_type != "code":
                continue
            cell_source: str = cell.source
            lines = cell_source.splitlines()
            if lines and lines[-1] != self.DONE_STATEMENT:
                lines.append(self.DONE_STATEMENT)
            cell.source = linesep.join(lines)

    async def generate(self):
        """
        Generate the notebook by injecting parameters and clearing outputs.
        """
        await self.clear_notebook_outputs()
        await self.inject_key_value_data()
        await self.inject_done_statement()
        # Write the modified notebook to the output path
        nb_write(self.notebook, self.output_path)
