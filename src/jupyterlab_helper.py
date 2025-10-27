import json
import logging
from dataclasses import dataclass
from functools import cached_property
from typing import Any

import requests
from requests.exceptions import RequestException

logger: logging.Logger = logging.getLogger(__name__)
# Default level is INFO
logger.setLevel(logging.INFO)
console_handler: logging.StreamHandler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


@dataclass(frozen=True, eq=False)
class JupyterLabHelper:
    """Helper class to interact with JupyterLab."""

    url: str
    token: str

    @cached_property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.token}",
            "Content-Type": "application/json",
        }

    def get_notebook_filename(self, notebook_path: str) -> str:
        """
        Extract the notebook filename from the given path.
        Parameters
        ----------
        notebook_path : str
            Path to the notebook file.
        Returns
        -------
        str
            The notebook filename.
        """
        return notebook_path.split("/")[-1]

    def get_notebook_url(self, notebook_path: str) -> str:
        """
        Get the full URL to access a notebook in JupyterLab.
        Parameters
        ----------
        notebook_path : str
            Path to the notebook file.
        Returns
        -------
        str
            Full URL to access the notebook.
        """
        return (
            f"{self.url}/lab/tree/"
            f"{self.get_notebook_filename(notebook_path)}/?token={self.token}"
        )

    def clear_all_jupyterlab_sessions(self) -> None:
        """
        Clear all active sessions (notebooks, consoles, terminals) in the
        JupyterLab instance.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get a list of all running sessions
            sessions_url: str = f"{self.url}/api/sessions"
            response: requests.Response = requests.get(
                sessions_url, headers=self.headers
            )
            response.raise_for_status()
            sessions: list[dict[str, Any]] = response.json()

            if not sessions:
                logger.info("No active sessions found.")
                return

            logger.info(f"Found {len(sessions)} active sessions. Shutting them down...")

            # Shut down each session
            for session in sessions:
                session_id: str = session["id"]
                shutdown_url: str = f"{self.url}/api/sessions/{session_id}"
                shutdown_response: requests.Response = requests.delete(
                    shutdown_url, headers=self.headers
                )
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

        except RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    def get_kernel_id_from_name(self, kernel_name: str) -> str | None:
        """
        Get the kernel ID for a given kernel name.
        Parameters
        ----------
        kernel_name : str
            The name of the kernel.
        Returns
        -------
        str | None
            The kernel ID if found, else None.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get the list of all kernels
            kernels_url: str = f"{self.url}/api/kernels"
            response: requests.Response = requests.get(
                kernels_url, headers=self.headers
            )
            response.raise_for_status()
            kernels: list[dict[str, Any]] = response.json()

            # Find the kernel ID for the given kernel name
            for kernel in kernels:
                if kernel["name"] == kernel_name:
                    return kernel["id"]

            logger.warning(f"No active kernel found for kernel name: {kernel_name}.")
            return None

        except RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    def restart_kernel(self, kernel_name: str) -> None:
        """
        Restart the kernel for a given kernel name.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        kernel_id = self.get_kernel_id_from_name(kernel_name)
        try:
            # Restart the kernel
            restart_url: str = f"{self.url}/api/kernels/{kernel_id}/restart"
            restart_response: requests.Response = requests.post(
                restart_url, headers=self.headers
            )
            restart_response.raise_for_status()

            logger.info(f"Kernel {kernel_id} restarted successfully.")

        except RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    def get_kernel_usage(self, kernel_id: str) -> dict[str, Any]:
        """
        Get the usage information for a specific kernel.
        Parameters
        ----------
        kernel_id : str
            The ID of the kernel.
        Returns
        -------
        dict[str, Any]
            The usage information for the kernel.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Get the usage info for a specific kernel
            kernel_usage_url: str = (
                f"{self.url}/api/metrics/v1/kernel_usage/get_usage/{kernel_id}"
            )
            response: requests.Response = requests.get(
                kernel_usage_url, headers=self.headers
            )
            response.raise_for_status()
            content: dict[str, Any] = response.json().get("content", {})

            logger.debug(f"Kernel usage info: {content}")

            return content

        except RequestException as e:
            logger.exception(f"Error communicating with JupyterLab server: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    def get_current_kernel_pid(self, kernel_id: str) -> int:
        return self.get_kernel_usage(kernel_id).get("pid")

    def upload_notebook(self, notebook_path: str) -> None:
        """
        Upload the notebook to the JupyterLab instance.
        Parameters
        ----------
        notebook_path : str
            Path to the notebook file to be uploaded.
        Raises
        ------
        FileNotFoundError
            If the notebook file does not exist.
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Extract filename from path
            notebook_filename: str = self.get_notebook_filename(notebook_path)
            upload_url: str = f"{self.url}/api/contents/{notebook_filename}"
            logger.info(f"Uploading notebook to {upload_url}")

            with open(notebook_path, "r", encoding="utf-8") as nb_file:
                notebook_content: dict[str, Any] = json.load(nb_file)

            payload: dict[str, Any] = {
                "content": notebook_content,
                "type": "notebook",
                "format": "json",
            }

            response: requests.Response = requests.put(
                upload_url, headers=self.headers, json=payload
            )
            response.raise_for_status()

            logger.info(f"Notebook uploaded successfully to {upload_url}")

        except FileNotFoundError as e:
            logger.exception(f"Notebook file not found: {notebook_path}")
            raise e
        except RequestException as e:
            logger.exception(f"Error uploading notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e

    def delete_notebook(self, notebook_filename: str) -> None:
        """
        Delete the notebook from the JupyterLab instance.
        Parameters
        ----------
        notebook_filename : str
            Name of the notebook file to be deleted.
        Raises
        ------
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            delete_url: str = f"{self.url}/api/contents/{notebook_filename}"
            logger.info(f"Deleting notebook at {delete_url}")

            response: requests.Response = requests.delete(
                delete_url, headers=self.headers
            )
            response.raise_for_status()

            logger.info(f"Notebook deleted successfully from {delete_url}")

        except RequestException as e:
            logger.exception(f"Error deleting notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e
