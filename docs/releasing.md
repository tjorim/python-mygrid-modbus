# Library releases

This package is released independently of the Home Assistant integration. Its metadata is prepared for `tjorim/mygrid-modbus` and PyPI project `mygrid-modbus`. No remote repository, PyPI project, or release was created by this extraction; availability of a PyPI name is not a reservation.

1. Confirm the GitHub repository and PyPI project name/ownership. Change package URLs if publishing under a different owner.
2. Run the README development checks and the supported-Python CI matrix, build wheel/sdist, and run `twine check` and `scripts/check_artifacts.py`. Verify that the wheel contains `mygrid_modbus/py.typed` and that neither artifact contains Home Assistant code or dependencies.
3. Record physical-device acceptance results before claiming hardware validation. Simulator results do not establish firmware behavior.
4. Set the package version in `pyproject.toml`, update the lockfile and release notes, and commit/tag the library version. Use an independent library version; do not tie every integration release to a library release.
5. Configure PyPI ownership/authentication or trusted publishing. Explicitly publish the reviewed wheel and sdist with `uv publish`. This is an external publication step; no credentials are stored in this repository and CI does not publish automatically.
6. Verify installation of `mygrid-modbus==0.1.0` in an empty environment from PyPI. Then update the integration manifest/project dependency to that version and test it before releasing the integration or submitting it to Home Assistant core.

Home Assistant core must resolve the library from the package index; a sibling-path development source is not used at runtime. Keep the public API documented, typed and backward compatible within a compatible release; release breaking API changes explicitly and adapt integration tests.

The base package accepts a caller-owned `ModbusUnit` and must remain backend-neutral. Validate base-only imports in a clean environment as well as standalone `[tmodbus]` / `[pymodbus]` use. The supported backends must not retry uncertain writes; rerun lost-acknowledgment tests when changing transport dependencies. Never add socket teardown to the battery client: the injected connection can have other consumers.
