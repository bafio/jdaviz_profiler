# Jdaviz Profiler

Jdaviz Profiler is a Python toolkit designed to automate the generation and profiling of Jupyter notebooks for the [jdaviz](https://github.com/spacetelescope/jdaviz) visualization suite.
It enables users to systematically test and benchmark jdaviz’s Imviz plugin under a variety of parameter combinations, such as image size, number of images, viewport size, and more.


## Features

### Notebook Generation:

Automatically creates Jupyter notebooks from a template (`template.ipynb`) and a parameter configuration file (`params.json`).

All possible combinations of parameters are generated, allowing for comprehensive profiling.

The `template.ipynb` file serves as the base notebook, while `params.json` contains the parameter values to be injected into the notebook.

The `template.ipynb` must have a cell with placeholders for the parameters to be replaced, therefore this cell must:
- precede all other cells with actual code using the parameters.
- be tagged with the `parameters` label.

Each parameter in the params.json file must have a corresponding placeholder in the template.ipynb file, and the placeholders must be unique having `_value` as suffix, e.g. `image_pixel_side_value` or `viewport_pixel_size_value` correspond to `image_pixel_side` or `viewport_pixel_size` parameter value used in the `template.ipynb`.

The generated parameterized notebooks will be saved in the `usecases/<usecase path>/notebooks` directory.

An example of how to structure a new `<usecase>` (along with `template.ipynb` and `params.json` files) is provided in this repository in `usecases/imviz_images`.

### Notebook Profiling:

Uses Selenium to launch and interact with JupyterLab, executing each notebook cell and recording performance metrics.
Optionally, if a cell is tagged with:
- `skip_profiling`, the performance metrics during the execution of that cell will not be collected.
- `wait_for_viz`, the profiler will wait after cell execution for Imviz to be stable (i.e. all images loaded and rendered) before proceeding to the next cell. This is useful for cells that load images into Imviz, ensuring accurate profiling of rendering times.

### Session Management:

Handles JupyterLab sessions, kernel restarts, notebook uploads, and clean-up automatically.

### Extensible:

Easily add new parameters or modify the template to test different scenarios, as well as create new `<usecases>` following the directives under "Notebook Generation".


## How It Works

1. **Parameter Setup**: Define the parameters and their possible values in `params.json`.
2. **Notebook Generation**: Run the notebook generator to create all combinations of notebooks in the output directory.
3. **Profiling**: Use the profiler to execute each notebook cell in a JupyterLab instance, collecting timing and output data for each cell.
4. **Results**: The profiling results can be saved in a structured format file (CSV) for analysis.


## Installation

To install, check out this repository and run:

```bash
pip install -e .
```

Python 3.12 or later is supported.

### Pre-commit hook

To install the `pre-commit` hook, simply run:
```bash
pip install ruff mypy types-requests types-psutil types-tqdm pre-commit
pre-commit install
```


## Usage

- The main scripts provided are:
    - `create_new_usecase.py`: Creates a new usecase directory with a template notebook and params file.
    - `notebooks_generator.py`: Generates notebooks from a usecase.
    - `notebook_profiler.py`: Profiles a specific notebook.
    - `generate_and_profile.py`: Generates all possible notebooks from a usecase and profiles all of them.
- Example usecases are provided in the `usecases/` directory.
- Create a new usecase:
    ```bash
    ./create_new_usecase.py --name <new usecase name>
    ```
- Generate all possible notebooks from a usecase:
    ```bash
    ./notebooks_generator.py --input_dir_path <usecase path>
    ```
    Additional arguments:
    - `--kernel_name`: Name of the kernel to be set in the generated notebooks (default: `python3`).
- Profile a specific notebook:
    ```bash
    ./notebook_profiler.py --url <JupyterLab URL> --token <API Token> --kernel_name <kernel name> --nb_input_path <notebook path>
    ```
    Additional arguments:
    - `--headless`: Run the browser in headless mode (default: `False`, same as `--no-headless`).
    - `--max_wait_time`: Max time to wait after executing each cell (in seconds, default: `300`).
    - `--screenshots_dir_path`: Path to the directory to where screenshots will be stored (default: `None`, no screenshot will be saved).
    - `--notebook_metrics_file_path`: Path to the file to where the notebook metrics will be stored. (default: `None`, no notebook metrics will be stored).
    - `--cell_metrics_file_path`: Path to the file to where the cell metrics will be stored. (default: `None`, no cell metrics will be stored).
- Generate all possible notebooks from a usecase and profile all of them:
    ```bash
    ./generate_and_profile.py --input_dir_path <usecase path> --url <JupyterLab URL> --token <API Token> --kernel_name <kernel name>
    ```
    Additional arguments:
    - `--headless`: Run the browser in headless mode (default: False, same as `--no-headless`).
    - `--max_wait_time`: Max time to wait after executing each cell (in seconds, default: `300`).
    - `--log_screenshots`: Whether to log screenshots or not (default: `False`, same as `--no-log_screenshots`).
    - `--save_metrics`: Whether to save profiling metrics to a CSV file (default: `False`, same as `--no-save_metrics`).

The profiling scripts assume that the JupyterLab instance is already running and accessible via the provided URL and token. Additionally, if the JupyterLab instance requires authentication, the username and password can be provided via environment variables or via a `.env` file:
```bash
JUPYTERLAB_USERNAME=<your_username>
JUPYTERLAB_PASSWORD=<your_password>
```

All scripts expose a `--log_level` argument to set the logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default is `INFO`), and a `--log_file` argument to specify a log file path (if not provided, logs will only be printed to the console).

All scripts have a `--help` option for more details on usage and available arguments.


## Dependencies

- `jdaviz`
- `pillow`
- `selenium`
- `chromedriver-py`
- `requests`
- `nbformat`
- `tqdm`
- `python-dotenv`


## License

BSD 3-Clause License
