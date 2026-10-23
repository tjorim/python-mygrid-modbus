# Library releases

The repository is `tjorim/python-mygrid-modbus` and the PyPI project is `mygrid-modbus`; nothing has been published to PyPI yet. Confirm name ownership before the first release. The version comes from git tags (hatch-vcs), so there is no version to edit.

1. Run the README checks and supported-Python matrix (`ruff`, `ty`, `pytest`). Build wheel/sdist, run `twine check` and the artifact checker, and review generated files and metadata. If a ModuleTwo is reachable with Modbus enabled, also run the read-only live smoke tests: `MYGRID_HOST=<ip> uv run pytest -m live`; record the result in the release notes (hardware validation is still pending).
2. Record release notes and push a tag `vX.Y.Z` on the reviewed commit. Consumers pin library releases independently of their own versions.
3. Configure PyPI trusted publishing for `.github/workflows/publish.yml` and the GitHub environment `pypi`. No API token is stored in source.
4. Pushing the tag runs the publish workflow (or dispatch it for an existing tag). It builds, tests, checks metadata, then publishes the reviewed artifacts through the protected environment.
5. Verify an empty-environment installation from PyPI, with and without each backend extra. Rerun lost-acknowledgment tests when updating transport dependencies.

Keep the unit API, field metadata and raw diagnostic format documented. Device communication and timing belong in this package; connection ownership belongs to its consumer. Never add socket cleanup to the device object. Physical-device results must be recorded before claiming firmware validation.
