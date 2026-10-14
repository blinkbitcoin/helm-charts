#!/usr/bin/env python3
"""Compare the package snapshot to its original index; never repair checksums.

Requires Python 3.11+ and Mike Farah yq v4 on PATH. No network requests.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


SOURCE = "https://github.com/blinkbitcoin/charts/releases/download/"
LEGACY = "https://github.com/GaloyMoney/charts/releases/download/"
DESTINATION = "https://blinkbitcoin.github.io/helm-charts/"
INPUTS = (
    "migration/original-index.yaml", "index.yaml", "migration/manifest.json",
    "migration/excluded-packages.json", "CHECKSUMS.sha256",
)


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(url):
    return SOURCE + url[len(LEGACY):] if url.startswith(LEGACY) else url


def exclusion_reason(refs, observed):
    digests = [ref.get("digest") for ref in refs]
    if not refs:
        return "not_in_original_index"
    if any(digest is None for digest in digests):
        return "missing_original_checksum"
    if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in digests):
        return "invalid_original_checksum"
    if len(set(digests)) != 1:
        return "conflicting_original_checksums"
    if digests[0] != observed:
        return "original_checksum_mismatch"
    return None


def entry_bag(entries):
    return Counter(json.dumps([name, entry], sort_keys=True)
                   for name, values in entries.items() for entry in values)


def verify(root, excluded_ref=None):
    report = {"scope": "Offline snapshot integrity, not release provenance or live download availability.",
              "verifier_sha256": sha256(Path(__file__)),
              "checks": [], "archives": [], "exclusions": []}

    def check(name, passed):
        report["checks"].append({"check": name, "passed": bool(passed)})

    if excluded_ref is not None:
        report["excluded_archive_commit"] = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--verify", "--end-of-options", excluded_ref + "^{commit}"],
            text=True, stderr=subprocess.PIPE).strip()
    report["input_sha256"] = {name: sha256(root / name) for name in INPUTS}
    original, candidate = (json.loads(subprocess.check_output(
        ["yq", "-o=json", ".", str(root / name)], stderr=subprocess.PIPE))
        for name in INPUTS[:2])
    manifest = json.loads((root / INPUTS[2]).read_text())
    excluded = json.loads((root / INPUTS[3]).read_text())
    packages = manifest["packages"]
    references = defaultdict(list)
    for chart, entries in original["entries"].items():
        for entry in entries:
            for url in entry["urls"]:
                references[canonical(url)].append(
                    {"chart": chart, "version": entry["version"], "digest": entry.get("digest")})
    checksum_lines = [line.split("  ", 1) for line in (root / INPUTS[4]).read_text().splitlines()]
    checksums = {path: digest for digest, path in checksum_lines}
    retained_paths = {package["path"] for package in packages}
    excluded_paths = {package["path"] for package in excluded}
    inventory = {path.relative_to(root).as_posix() for path in (root / "packages").rglob("*")
                 if path.is_symlink() or not path.is_dir()}
    check("original index hash matches manifest", report["input_sha256"][INPUTS[0]] == manifest["source_index_sha256"])
    check("manifest and exclusion paths are unique", len(retained_paths) == len(packages) and len(excluded_paths) == len(excluded))
    check("retained and excluded paths are disjoint", retained_paths.isdisjoint(excluded_paths))
    check("disk inventory equals retained manifest", inventory == retained_paths)
    check("checksum inventory equals retained manifest", set(checksums) == retained_paths and len(checksums) == len(checksum_lines))
    check("manifest counts match", manifest["package_count"] == len(packages) and manifest["excluded_package_count"] == len(excluded))
    check("every original URL is accounted for", set(references) <= {p["source"] for p in packages + excluded})
    source_paths = {}
    total_bytes = 0
    for package in packages + excluded:
        path = PurePosixPath(package["path"])
        safe = (len(path.parts) == 3 and path.parts[0] == "packages"
                and ".." not in path.parts and path.suffix == ".tgz"
                and not (root / path).is_symlink()
                and (root / path).resolve().is_relative_to((root / "packages").resolve()))
        check(f"{path}: safe package path", safe)
        if not safe:
            continue
        check(f"{path}: release URL and tag match path",
              package["source"] == SOURCE + "/".join(path.parts[1:]) and package["release_tag"] == path.parts[1])
        refs = references[package["source"]]
        result = {"path": str(path), "source": package["source"], "original_references": refs}
        if "reason" in package:
            result.update({"recorded_sha256": package["sha256"],
                           "reason": package["reason"], "bytes_rehashed": False})
            if excluded_ref is not None:
                historical = subprocess.check_output(
                    ["git", "-C", str(root), "show", report["excluded_archive_commit"] + ":" + str(path)],
                    stderr=subprocess.PIPE)
                result.update({"actual_sha256": hashlib.sha256(historical).hexdigest(),
                               "actual_size": len(historical), "bytes_rehashed": True})
                check(f"{path}: historical bytes match exclusion evidence",
                      result["actual_sha256"] == package["sha256"] and len(historical) == package["size"])
            check(f"{path}: excluded file is absent", not (root / path).exists())
            check(f"{path}: exclusion matches original evidence",
                  package["reason"] is not None and exclusion_reason(refs, package["sha256"]) == package["reason"] and refs == package["original_entries"])
            report["exclusions"].append(result)
            continue
        source_paths[package["source"]] = str(path)
        present = (root / path).is_file()
        actual_digest = sha256(root / path) if present else None
        actual_size = (root / path).stat().st_size if present else 0
        total_bytes += actual_size
        reason = exclusion_reason(refs, actual_digest)
        result.update({"actual_sha256": actual_digest, "manifest_sha256": package["sha256"],
                       "checksum_list_sha256": checksums.get(str(path)),
                       "actual_size": actual_size, "manifest_size": package["size"],
                       "passed": present and reason is None and actual_digest == package["sha256"] == checksums.get(str(path)) and actual_size == package["size"]})
        check(f"{path}: bytes match original index, manifest and checksum list", result["passed"])
        report["archives"].append(result)
    expected = defaultdict(list)
    for chart, entries in original["entries"].items():
        for entry in entries:
            urls = [canonical(url) for url in entry["urls"]]
            if all(url in source_paths for url in urls):
                expected[chart].append({**entry, "urls": [DESTINATION + source_paths[url] for url in urls]})
    check("candidate entries preserve all retained metadata except URLs", entry_bag(candidate["entries"]) == entry_bag(expected))
    check("candidate index API version is preserved", candidate["apiVersion"] == original["apiVersion"])
    check("manifest total bytes matches disk", manifest["total_bytes"] == total_bytes)
    report["summary"] = {"archives": len(packages), "index_entries": sum(len(v) for v in candidate["entries"].values()),
                         "bytes": total_bytes, "excluded_archives": len(excluded),
                         "removed_original_index_entries": sum(len(v) for v in original["entries"].values()) - sum(len(v) for v in candidate["entries"].values())}
    report["passed"] = all(item["passed"] for item in report["checks"])
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--excluded-ref", help="Git commit containing excluded bytes to rehash without restoring them")
    parser.add_argument("--report", required=True, type=Path, help="JSON output path outside packages and the verification inputs")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.report.resolve()
    if output in {(root / name).resolve() for name in INPUTS} or output.is_relative_to((root / "packages").resolve()):
        parser.error("report must not overwrite verification inputs or packages")
    try:
        report = verify(root, args.excluded_ref)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        report = {"passed": False, "input_error": str(error)}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print("PASS" if report["passed"] else "FAIL")
    print(json.dumps(report.get("summary", {}), sort_keys=True))
    for item in report.get("checks", []):
        if not item["passed"]:
            print("FAILED: " + item["check"])
    for item in report.get("exclusions", []):
        evidence = "rehashed from Git; absent from packages" if item["bytes_rehashed"] else "recorded hash; bytes absent"
        print(f"EXCLUDED {item['path']}: {item['reason']} ({evidence})")
    if "input_error" in report:
        print("INPUT ERROR: " + report["input_error"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
