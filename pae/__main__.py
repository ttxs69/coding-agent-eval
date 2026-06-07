"""Allow `python -m pae` to invoke the CLI."""

from pae.cli import main

raise SystemExit(main())
