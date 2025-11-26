The layout of this package was initially generated using the
[scikit-hep/cookie][cookie] package which follows the [Scikit-HEP
Developer][skhep-dev-intro] recommendations for modern "dual-stack" python plus
C++ packages. Thanks goes to Henry Schreiner (@henryiii) for putting together
these recommendations and examples.

[cookie]: https://github.com/scikit-hep/cookie
[skhep-dev-intro]: https://scikit-hep.org/developer/intro

A detailed overview of the architecture of this package is available in
[ARCHITECTURE.md](./ARCHITECTURE.md).

# Setting up a development environment

You can set up a development environment by running:

```bash
python3 -m venv .env
source .env/bin/activate
pip install -e . --group dev
```

Alternatively, you can use `uv`:

```bash
uv sync --no-editable
source .venv/bin/activate
```

The `--no-editable` flag is needed to avoid installing the package in editable
mode, as the paths to the library and include files are not correctly set up for
editable installs, preventing C++ compilation.

# Post setup

You should prepare pre-commit, which will help you by checking that commits pass
required checks:

```bash
pre-commit install # Will install a pre-commit hook into the git repo
```

You can also/alternatively run `pre-commit run` (changes only) or
`pre-commit run --all-files` to check even without installing the hook.

# Testing

Use PyTest to run the unit checks:

```bash
pytest
```

# Building docs

From inside your environment with the `docs` extra installed (i.e.
`pip install .[docs]`), run:

```bash
cd docs
make clean && rm -rf _generated
make
```

# Conversion routines

The generic conversion routines require the `convert` extra to be installed.

# Maintainer notes

A nice commit summary can be generated from the main branch via:

```bash
git log --pretty="format: - %s" $(git describe --tags --abbrev=0)..HEAD
```
