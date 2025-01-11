# Contributing to PyOutlineAPI

Thank you for considering contributing to PyOutlineAPI! Whether you have suggestions, bug reports, or code improvements,
your input is valuable.

## How to Contribute

### Reporting Issues

If you encounter any issues or bugs, please follow these steps:

1. **Search for Existing Issues**: Check the [Issues](https://github.com/orenlab/pyoutlineapi/issues) section to see if
   your issue has already been reported.
2. **Create a New Issue**: If you don't find an existing
   issue, [open a new issue](https://github.com/orenlab/pyoutlineapi/issues/new) with:
    - A descriptive title
    - Steps to reproduce the issue
    - Expected and actual results
    - Python version (3.10+) and PyOutlineAPI version
    - Any relevant code snippets or error messages
    - Environment details (OS, Outline server version)

### Suggesting Enhancements

For new feature or improvement suggestions:

1. **Check Existing Feature Requests**: Review the [Issues](https://github.com/orenlab/pyoutlineapi/issues) to see if
   similar features have been suggested.
2. **Open a New Feature Request**: [Submit a new feature request](https://github.com/orenlab/pyoutlineapi/issues/new)
   with:
    - A descriptive title
    - Detailed description of the proposed feature
    - Use cases and benefits
    - Example code or API design if applicable

### Contributing Code

To contribute code:

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/orenlab/pyoutlineapi.git
   cd pyoutlineapi
   ```

2. **Set Up Development Environment**:
   ```bash
   # Install Poetry if you haven't already
   curl -sSL https://install.python-poetry.org | python3 -

   # Install dependencies
   poetry install --with dev

   # Activate virtual environment
   poetry shell
   ```

3. **Create a Feature Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-description
   ```

4. **Make Your Changes**:
    - Follow the existing code structure
    - Use type hints consistently (Python 3.10+ typing features)
    - Add docstrings with examples (see existing code)
    - Update tests if needed

5. **Test Your Changes**:
   ```bash
   # Run tests with coverage
   poetry run pytest

   # Type checking
   poetry run mypy pyoutlineapi

   # Code formatting
   poetry run black pyoutlineapi tests

   # Linting
   poetry run flake8 pyoutlineapi tests
   ```

6. **Submit a Pull Request**:
    - Write a clear PR description
    - Link related issues
    - Include any necessary documentation updates

## Code Style Guidelines

We follow strict coding standards to maintain consistency:

### Python Style

- Follow [PEP 8](https://pep8.org/) conventions
- Use modern type hints (Python 3.10+)
- Maximum line length: 88 characters (Black default)
- Use descriptive variable names

### Documentation

- Use Google-style docstrings with type information
- For non-private methods, include examples in docstrings (see existing code)
- Example:
  ```python
  async def create_access_key(
      self,
      *,
      name: Optional[str] = None,
      port: Optional[int] = None,
  ) -> Union[JsonDict, AccessKey]:
      """
      Create a new access key.

      Args:
          name: Optional key name
          port: Optional port number (1-65535)

      Returns:
          New access key details

      Examples:
          >>> async with AsyncOutlineClient(...) as client:
          ...     key = await client.create_access_key(name="User 1")
          ...     print(f"Created key: {key.access_url}")
      """
  ```

### Testing

- Write unit tests for new features
- Use pytest fixtures and parametrize when appropriate
- Mock external dependencies
- Maintain high test coverage (enforced by pytest-cov)

### Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style/formatting changes
- `refactor`: Code refactoring
- `test`: Adding/updating tests
- `chore`: Maintenance tasks

Example:

```
feat(client): add support for custom encryption methods

- Added method parameter to create_access_key
- Updated documentation with examples
- Added unit tests for new functionality

Closes #123
```

## Development Setup

1. **Required Dependencies**:
    - Python 3.10 or higher
    - Poetry for package management
    - Outline VPN server (for integration testing)

2. **Development Tools**:
   All development dependencies are managed by Poetry and include:
    - pytest-cov for test coverage
    - black for code formatting
    - mypy for type checking
    - flake8 for linting

## Project Configuration

Key project settings are managed in `pyproject.toml`, including:

- Python version requirement (3.10+)
- Dependencies:
    - pydantic (^2.9.2)
    - aiohttp (^3.11.11)
- Development dependencies for testing and code quality
- Pytest configuration with coverage reporting

## Contact

- **Issues**: [GitHub Issues](https://github.com/orenlab/pyoutlineapi/issues)
- **Email**: `pytelemonbot@mail.ru`

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

Thank you for contributing to PyOutlineAPI!