def main() -> None:
    import os
    from .chatgpt_runtime import enabled, self_hosted_enabled

    if enabled() and self_hosted_enabled():
        from .chatgpt_cli import serve_api
        serve_api(os.getenv("INKU_SERVER_HOST", "127.0.0.1"),
                  int(os.getenv("INKU_SERVER_PORT", "8100")), self_hosted=True)
        return
    from .api import main as api_main

    api_main()

__all__ = ["main"]
