import json
import logging

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Default level is INFO
console_handler = logging.StreamHandler()
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logger.addHandler(console_handler)


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
        RequestException
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

        except RequestException as e:
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
        RequestException
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

        except RequestException as e:
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
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Extract filename from path
            notebook_path = self.nb_input_path.split("/")[-1]
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
        except RequestException as e:
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
        RequestException
            If there is an error communicating with the JupyterLab server.
        Exception
            For any other unexpected errors.
        """
        try:
            # Extract filename from path
            notebook_path = self.nb_input_path.split("/")[-1]
            delete_url = f"{self.url}/api/contents/{notebook_path}"
            logger.info(f"Deleting notebook at {delete_url}")

            response = requests.delete(delete_url, headers=self.headers)
            response.raise_for_status()

            logger.info(f"Notebook deleted successfully from {delete_url}")

        except RequestException as e:
            logger.exception(f"Error deleting notebook: {e}")
            raise e
        except Exception as e:
            logger.exception(f"An unexpected error occurred: {e}")
            raise e
