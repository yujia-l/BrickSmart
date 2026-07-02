"""Model-neutral module name for the generic structural build CLI."""
from bricksmart.build_cli import build_parser, main

__all__ = ["build_parser", "main"]

if __name__ == "__main__":
    main()
