# sample

Fixture project for testing the self-improve skill's forward mode. Contains intentionally seeded forward signals — see `self-improve-skill/tests/test_fixture_project.py` for the catalog.

The fixture also retains its v1 reactive seeds (an off-by-one bug in `add()`, a missing-test target in `public_api_function`, etc.) — those are inert under forward mode but don't hurt.

## Planned features

- **Subtraction (`subtract(a, b)`)** — referenced in source docstring but not yet implemented
- **Division (`divide(a, b)`)** — would parallel `multiply` and complete the basic four arithmetic ops
