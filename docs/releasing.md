# Library releases

The package is prepared for repository `tjorim/mygrid-modbus` and PyPI project `mygrid-modbus`. No repository or package has been published. Confirm name ownership before the first release.

1. Run the README checks and supported-Python matrix. Build wheel/sdist, run `twine check` and the artifact checker, and review generated files and version metadata.
2. Update `project.version`, refresh the lockfile and record release notes. The tag must match the version, e.g. `v0.1.0`. Consumers pin library releases independently of their own versions.
3. Configure PyPI trusted publishing for `.github/workflows/publish.yml` and the GitHub environment `pypi`. No API token is stored in source.
4. Publish a GitHub release for the reviewed tag, or manually dispatch the workflow for that existing tag. It builds, tests, checks metadata, then publishes the reviewed artifacts through the protected environment.
5. Verify an empty-environment installation from PyPI, with and without each backend extra. Rerun lost-acknowledgment tests when updating transport dependencies.

Keep the unit API, field metadata and raw diagnostic format documented. Device communication and timing belong in this package; connection ownership belongs to its consumer. Never add socket cleanup to the device object. Physical-device results must be recorded before claiming firmware validation.
