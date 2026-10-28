import json
import sys

from app.main import create_app
from app.settings import Settings


def main() -> None:
    settings = Settings(
        _env_file=None, env="test", database_url="sqlite:///:memory:", guest_access=True
    )
    app = create_app(settings)
    json.dump(app.openapi(), sys.stdout, indent=2)


if __name__ == "__main__":
    main()
