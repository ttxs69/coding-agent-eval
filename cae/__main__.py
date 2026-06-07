"""Allow `python -m cae` to invoke the CLI."""

from cae.cli import main

raise SystemExit(main())
