See the [Scikit-HEP Developer introduction][skhep-dev-intro] for a
detailed description of best practices for developing Scikit-HEP packages.

[skhep-dev-intro]: https://scikit-hep.org/developer/intro

# Setting up a development environment

You can set up a development environment by running:

```bash
python3 -m venv .env
source ./.env/bin/activate
pip install -e .[dev,test]
```

# Post setup

You should prepare pre-commit, which will help you by checking that commits
pass required checks:

```bash
pre-commit install # Will install a pre-commit hook into the git repo
```

You can also/alternatively run `pre-commit run` (changes only) or `pre-commit
run --all-files` to check even without installing the hook.

# Testing

Use PyTest to run the unit checks:

```bash
pytest
```

# Building docs

You can build the docs using:


From inside your environment with the docs extra installed, run:

```bash
sphinx-build -M html docs docs/_build
```
