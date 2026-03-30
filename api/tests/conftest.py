import warnings


warnings.filterwarnings(
    "ignore",
    message=r"Please use `import python_multipart` instead\.",
    category=PendingDeprecationWarning,
    module=r"starlette\.formparsers",
)


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "filterwarnings",
        r"ignore:Please use `import python_multipart` instead\.:PendingDeprecationWarning:starlette\.formparsers",
    )
