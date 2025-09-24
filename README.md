# Jdaviz Profiler

Jdaviz Profiler is a Python toolkit designed to automate the generation and profiling of Jupyter notebooks for the [jdaviz](https://github.com/spacetelescope/jdaviz) visualization suite. It enables users to systematically test and benchmark jdaviz’s Imviz plugin under a variety of parameter combinations, such as image size, number of images, viewport size, and more.


## Features

### Notebook Generation:

Automatically creates Jupyter notebooks from a template (`template.ipynb`) and a parameter configuration file (`params.yaml`).

All possible combinations of parameters are generated, allowing for comprehensive profiling.

The `template.ipynb` file serves as the base notebook, while `params.yaml` contains the parameter values to be injected into the notebook.

The `template.ipynb` must have a cell with placeholders for the parameters to be replaced, therefore this cell must:
- precede all other cells with actual code using the parameters.
- be tagged with the `parameters` label.

Each parameter in the params.yaml file must have a corresponding placeholder in the template.ipynb file, and the placeholders must be unique having `_value` as suffix, e.g. `image_pixel_side_value` or `viewport_pixel_size_value`.

The generated parameterized notebooks will be saved in the `<usecase path>/notebooks` directory.

An example of how to structure a new `<usecase>`, and the `template.ipynb` and `params.yaml` files, is provided in this repository in `imviz_images`.

### Notebook Profiling:

Uses Playwright to launch and interact with JupyterLab, executing each notebook cell and recording performance metrics.

### Session Management:

Handles JupyterLab sessions, kernel restarts, notebook uploads, and clean-up automatically.

### Extensible:

Easily add new parameters or modify the template to test different scenarios, as well as create new `<usecases>` following the directives under "Notebook Generation".


## How It Works

1. **Parameter Setup**: Define the parameters and their possible values in `params.yaml`.
2. **Notebook Generation**: Run the notebook generator to create all combinations of notebooks in the output directory.
3. **Profiling**: Use the profiler to execute each notebook cell in a JupyterLab instance, collecting timing and output data for each cell.


## Installation

To install, check out this repository and run:

```bash
pip install -e .
```

Python 3.12 or later is supported.


### Pre-commit hook

To install the pre-commit hook, simply run:
```bash
pre-commit install
```


## Usage

- Generate notebooks:
    ```bash
    python notebooks_generator.py --input_dir_path <usecase path>
    ```
- Profile notebooks:
    ```bash
    python notebook_profiler.py --url <JupyterLab URL> --token <API Token> --kernel_name <kernel name> --nb_input_path <notebook path>
    ```
- Or run both steps together:
    ```bash
    python generate_and_profile.py --input_dir_path <usecase path> --url <JupyterLab URL> --token <API Token> --kernel_name <kernel name>
    ```


## Dependencies

- `jdaviz`
- `pillow`
- `playwright`
- `requests`
- `nbformat`
- `PyYAML`
- `ruff`
- `pre-commit`


## License

BSD 3-Clause License
