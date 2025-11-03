import logging
from dataclasses import dataclass
from functools import cached_property
from os import linesep
from typing import Any, ClassVar

from nbformat import NO_CONVERT
from nbformat import read as nb_read
from nbformat import reads as nb_reads
from nbformat import write as nb_write
from nbformat import writes as nb_writes

from src.utils import get_logger

# Initialize logger
logger: logging.Logger = get_logger()


@dataclass(frozen=True, eq=False)
class NotebookGenerator:
    """
    A class to generate Jupyter notebooks by filling in parameters in a
    template notebook file.
    Attributes
    ----------
    template_path : str
        Path to the template notebook file.
    """

    template_path: str

    PARAMS_CELL_TAG: ClassVar[str] = "parameters"
    DONE_STATEMENT: ClassVar[str] = 'print("DONE")'

    @staticmethod
    def add_statement_to_cell_source(statement: str, cell_source: str) -> str:
        """
        Adds a statement to the end of a code cell's source.
        Parameters
        ----------
        statement : str
            The statement to add.
        cell_source : str
            The original source code of the cell.
        Returns
        -------
        str
            The modified source code with the statement added at the end.
        """
        if (lines := cell_source.splitlines()) and lines[-1] != statement:
            lines.append(statement)
        cell_source = linesep.join(lines)
        return cell_source

    @cached_property
    def preprocessed_nb_template_raw_content(self) -> str:
        """
        Preprocess the notebook template by retaining only code cells, clearing outputs,
        resetting execution counts, and adding a done statement to each cell.
        Returns
        -------
        str
            The raw content of the preprocessed notebook template.
        """
        notebook = nb_read(self.template_path, NO_CONVERT)
        notebook.cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
        for cell in notebook.cells:
            # Clear the outputs
            cell.outputs = []
            # Clear the execution_count
            cell.execution_count = None
            # Add the done_statement at the end of a cell source code
            cell.source = self.add_statement_to_cell_source(
                self.DONE_STATEMENT, cell.source
            )
            # Make the cell non-editable
            cell.metadata["editable"] = False
        return nb_writes(notebook)

    def generate_and_save(
        self, parameters_values: dict[str, Any], output_path: str
    ) -> None:
        """
        Generate a notebook by filling in the parameters in the template and save it to
        the specified output path.
        Parameters
        ----------
        parameters_values : dict[str, Any]
            Dictionary containing parameter names and their values.
        output_path : str
            Path to the output notebook file.
        Raises
        ------
        ValueError
            If no cell with the `PARAMS_CELL_TAG` tag is found.
            If the cell with the `PARAMS_CELL_TAG` tag is found with no content.
        """
        notebook = nb_reads(self.preprocessed_nb_template_raw_content, NO_CONVERT)
        param_cell_found: bool = False
        for cell in notebook.cells:
            # Get the notebook cell tagged with the specified `PARAMS_CELL_TAG`
            if self.PARAMS_CELL_TAG in cell.metadata.get("tags", []):
                param_cell_found = True
                if not cell.source:
                    raise ValueError(
                        f"'{self.PARAMS_CELL_TAG}' cell found with "
                        "no content in the notebook."
                    )
                cell.source = cell.source.format(**parameters_values)

        if not param_cell_found:
            raise ValueError(
                f"No cell with '{self.PARAMS_CELL_TAG}' tag found in the notebook."
            )

        # Write the modified notebook to the output path
        nb_write(notebook, output_path)
