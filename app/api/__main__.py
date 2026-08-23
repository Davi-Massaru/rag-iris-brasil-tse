from app.config import get_settings

from .app import create_app


def main() -> None:
    settings = get_settings()
    create_app(settings).run(host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
