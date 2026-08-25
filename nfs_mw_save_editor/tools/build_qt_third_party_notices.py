"""Build a consolidated Qt Base third-party notice from an official source tree."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


NON_WINDOWS_OR_UNSHIPPED_COMPONENTS = {
    "Cocoa Platform Plugin",
    "DejaVu Fonts",
    "Native Style for Android",
    "QEventDispatcher on macOS",
    "WebGradients",
    "XCB-XInput",
    "forkfd",
}

LICENSE_FILE_BY_ID = {
    "Apache-2.0": "Apache-2.0.txt",
    "BSD-2-Clause": "BSD-2-Clause.txt",
    "BSD-3-Clause": "BSD-3-Clause.txt",
    "CC0-1.0": "CC0-1.0.txt",
    "FTL": "FTL.txt",
    "GPL-2.0-only": "GPL-2.0-only.txt",
    "IJG": "IJG.txt",
    "Imlib2": "Imlib2.txt",
    "Libpng": "Libpng.txt",
    "LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception": (
        "LicenseRef-BSD-3-Clause-with-PCRE2-Binary-Like-Packages-Exception.txt"
    ),
    "LicenseRef-ICC-License": "LicenseRef-ICC-License.txt",
    "LicenseRef-Lcs-Telegraphics": "LicenseRef-Lcs-Telegraphics.txt",
    "LicenseRef-SHA1-Public-Domain": "LicenseRef-SHA1-Public-Domain.txt",
    "MIT": "MIT.txt",
    "MIT-open-group": "MIT-open-group.txt",
    "Unicode-3.0": "Unicode-3.0.txt",
    "Zlib": "Zlib.txt",
    "libpng-2.0": "libpng-2.0.txt",
}


def _attributions(qtbase_root: Path) -> list[tuple[Path, dict]]:
    result: list[tuple[Path, dict]] = []
    for path in sorted(qtbase_root.rglob("qt_attribution.json")):
        data = json.loads(path.read_text(encoding="utf-8"), strict=False)
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            if entry.get("QDocModule") not in {"qtcore", "qtgui"}:
                continue
            if "tools" in entry.get("QtParts", []):
                continue
            if entry.get("Name") in NON_WINDOWS_OR_UNSHIPPED_COMPONENTS:
                continue
            result.append((path, entry))
    return result


def _license_paths(qtbase_root: Path, attribution_path: Path, entry: dict) -> list[Path]:
    value = entry.get("LicenseFile")
    names = value if isinstance(value, list) else ([value] if value else [])
    paths = [(attribution_path.parent / name).resolve() for name in names]
    paths = [path for path in paths if path.is_file()]
    if paths:
        return paths

    result: list[Path] = []
    for license_id in re.split(r"\s+(?:AND|OR)\s+", entry.get("LicenseId", "")):
        filename = LICENSE_FILE_BY_ID.get(license_id)
        if filename:
            path = qtbase_root / "LICENSES" / filename
            if path.is_file():
                result.append(path)
    if not result:
        raise RuntimeError(f"No license text for {entry.get('Name')!r}")
    return result


def build_notice(qtbase_root: Path) -> str:
    component_refs: list[tuple[dict, list[str]]] = []
    license_texts: dict[str, dict[str, object]] = {}

    for attribution_path, entry in _attributions(qtbase_root):
        refs: list[str] = []
        for license_path in _license_paths(qtbase_root, attribution_path, entry):
            content = license_path.read_text(encoding="utf-8-sig").strip()
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            record = license_texts.setdefault(digest, {"content": content, "sources": []})
            source = license_path.relative_to(qtbase_root).as_posix()
            sources = record["sources"]
            if source not in sources:
                sources.append(source)
            refs.append(digest)
        component_refs.append((entry, refs))

    text_ids = {digest: f"L{index:02d}" for index, digest in enumerate(license_texts, 1)}
    lines = [
        "Qt 6.10.1 third-party notices and license texts",
        "",
        "This file conservatively covers third-party components attributed by Qt",
        "to Qt Core and Qt GUI, the Qt libraries distributed with NFS MW Save",
        "Editor. It was assembled from the qt_attribution.json and LICENSES files",
        "in the official Qt Base 6.10.1 source archive whose SHA-256 is documented",
        "in QT_LGPL_COMPLIANCE.md. Components specific to non-Windows platforms,",
        "tools, tests, or removed plugins are not included.",
        "",
        "COMPONENT ATTRIBUTIONS",
        "======================",
        "",
    ]
    for index, (entry, refs) in enumerate(component_refs, 1):
        lines.append(f"{index}. {entry.get('Name')}")
        if entry.get("Version"):
            lines.append(f"   Version: {entry['Version']}")
        if entry.get("Homepage"):
            lines.append(f"   Homepage: {entry['Homepage']}")
        lines.append(f"   License: {entry.get('License')}")
        copyright_lines = entry.get("Copyright", [])
        if isinstance(copyright_lines, str):
            copyright_lines = [copyright_lines]
        for block in copyright_lines:
            for copyright_line in block.splitlines():
                lines.append(f"   {copyright_line}")
        lines.append("   Full text: " + ", ".join(text_ids[ref] for ref in refs))
        lines.append("")

    lines.extend(("FULL LICENSE TEXTS", "==================", ""))
    for digest, record in license_texts.items():
        lines.append(text_ids[digest])
        lines.append("Source file(s): " + ", ".join(record["sources"]))
        lines.append("-" * 72)
        lines.append(record["content"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("qtbase_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(build_notice(args.qtbase_root.resolve()), encoding="utf-8")


if __name__ == "__main__":
    main()
