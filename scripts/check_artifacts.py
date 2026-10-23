"""Check the wheel/sdist boundary before a library release."""

import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Ensure artifacts carry typing and only the independent protocol package."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    with zipfile.ZipFile(
        ROOT / "dist" / f"mygrid_modbus-{version}-py3-none-any.whl"
    ) as wheel:
        names = wheel.namelist()
        assert "mygrid_modbus/py.typed" in names
        assert "mygrid_modbus/__init__.py" in names
        assert "mygrid_modbus/client.py" in names
        assert all(
            name.startswith(("mygrid_modbus/", f"mygrid_modbus-{version}.dist-info/"))
            for name in names
        )
        metadata = BytesParser().parsebytes(
            wheel.read(f"mygrid_modbus-{version}.dist-info/METADATA")
        )
        assert metadata["Name"] == project["name"]
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.12"
        assert metadata.get_all("Requires-Dist") == ["pymodbus<4,>=3.13.1"]
    with tarfile.open(ROOT / "dist" / f"mygrid_modbus-{version}.tar.gz") as sdist:
        names = sdist.getnames()
        assert any(name.endswith("/src/mygrid_modbus/py.typed") for name in names)
        assert not any("custom_components/" in name for name in names)
    print(
        "Wheel and sdist contain the independent typed library and expected metadata."
    )


if __name__ == "__main__":
    main()
