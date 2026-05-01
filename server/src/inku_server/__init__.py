def main() -> None:
    from .api import main as api_main

    api_main()

__all__ = ["main"]
