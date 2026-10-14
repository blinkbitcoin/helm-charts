"""Small synthetic snapshots exercise integrity failures without editing archives."""

from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import verify_archives as verifier


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "migration").mkdir()
        self.path = "packages/demo-v1/demo-1.tgz"
        archive = self.root / self.path
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b"archive bytes")
        self.digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.entry = {"name": "demo", "version": "1", "digest": self.digest,
                      "urls": [verifier.LEGACY + "demo-v1/demo-1.tgz"]}
        self.original = {"apiVersion": "v1", "entries": {"demo": [self.entry]}}
        self.candidate = {"apiVersion": "v1", "entries": {"demo": [dict(self.entry, urls=[verifier.DESTINATION + self.path])]}}
        self.package = {"path": self.path, "sha256": self.digest, "size": 13,
                        "source": verifier.SOURCE + "demo-v1/demo-1.tgz", "release_tag": "demo-v1"}
        self.manifest = {"package_count": 1, "excluded_package_count": 0,
                         "total_bytes": 13, "packages": [self.package]}
        self.excluded = []
        self.checksums = f"{self.digest}  {self.path}\n"
        self.write()

    def write(self):
        # JSON is valid YAML and is parsed through the real yq command.
        original = self.root / "migration/original-index.yaml"
        original.write_text(json.dumps(self.original))
        self.manifest["source_index_sha256"] = verifier.sha256(original)
        for name, data in [("index.yaml", self.candidate), ("migration/manifest.json", self.manifest),
                           ("migration/excluded-packages.json", self.excluded)]:
            (self.root / name).write_text(json.dumps(data))
        (self.root / "CHECKSUMS.sha256").write_text(self.checksums)

    def failed(self, check):
        self.write()
        report = verifier.verify(self.root)
        self.assertFalse(report["passed"])
        self.assertTrue(any(check in item["check"] and not item["passed"] for item in report["checks"]), report)

    def test_valid_and_cli_report(self):
        output = self.root / "report.json"
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(verifier.main(["--root", str(self.root), "--report", str(output)]), 0)
        report = json.loads(output.read_text())
        self.assertTrue(report["passed"])
        self.assertEqual(report["archives"][0]["actual_sha256"], self.digest)
        self.assertIn("PASS", stdout.getvalue())

    def test_corrupted_and_missing_archive(self):
        (self.root / self.path).write_bytes(b"corrupted")
        self.failed("bytes match original")
        (self.root / self.path).unlink()
        self.failed("disk inventory")

    def test_unexpected_file(self):
        (self.root / "packages/extra.txt").write_text("unexpected")
        self.failed("disk inventory")

    def test_unexpected_symlink_directory(self):
        (self.root / "packages/extra").symlink_to(self.root / "migration", target_is_directory=True)
        self.failed("disk inventory")

    def test_duplicate_manifest(self):
        self.manifest["packages"].append(dict(self.package))
        self.failed("paths are unique")

    def test_bad_counts(self):
        self.manifest["package_count"] = 2
        self.failed("manifest counts")

    def test_checksum_inventory_and_values(self):
        self.checksums += self.checksums
        self.failed("checksum inventory")
        self.checksums = ""
        self.failed("checksum inventory")
        self.checksums = f"{'0' * 64}  {self.path}\n"
        self.failed("bytes match original")

    def test_original_hash(self):
        (self.root / "migration/original-index.yaml").write_text(json.dumps(self.original) + "\n")
        report = verifier.verify(self.root)
        self.assertFalse(report["checks"][0]["passed"])

    def test_manifest_size_and_digest(self):
        self.package["size"] = 100
        self.failed("bytes match original")
        self.package["size"] = 13
        self.package["sha256"] = "0" * 64
        self.failed("bytes match original")

    def test_unaccounted_original_url(self):
        self.entry["urls"] = [verifier.SOURCE + "missing-v1/missing-1.tgz"]
        self.failed("every original URL")

    def test_path_traversal_and_symlink(self):
        for unsafe in ["../outside.tgz", "packages/../outside.tgz", "/absolute/file.tgz", "packages/demo-v1/file.zip"]:
            self.package["path"] = unsafe
            self.failed("safe package path")
        self.package["path"] = self.path
        (self.root / self.path).unlink()
        (self.root / "outside").write_bytes(b"archive bytes")
        (self.root / self.path).symlink_to(self.root / "outside")
        self.failed("safe package path")

    def test_release_url_and_tag(self):
        self.package["release_tag"] = "wrong"
        self.failed("release URL and tag")
        self.package["release_tag"] = "demo-v1"
        self.package["source"] += "?wrong"
        self.failed("release URL and tag")

    def test_symlink_parent_cannot_escape_packages(self):
        (self.root / self.path).unlink()
        (self.root / self.path).parent.rmdir()
        (self.root / "outside").mkdir()
        (self.root / "outside/demo-1.tgz").write_bytes(b"archive bytes")
        (self.root / self.path).parent.symlink_to(self.root / "outside", target_is_directory=True)
        self.failed("safe package path")

    def test_metadata_url_api_and_missing_entry(self):
        self.candidate["entries"]["demo"][0]["description"] = "changed"
        self.failed("preserve all retained metadata")
        del self.candidate["entries"]["demo"][0]["description"]
        self.candidate["entries"]["demo"][0]["urls"] = ["https://wrong.invalid/demo.tgz"]
        self.failed("preserve all retained metadata")
        self.candidate["apiVersion"] = "v2"
        self.failed("API version")
        self.candidate["entries"] = {}
        self.failed("preserve all retained metadata")

    def test_retained_bad_original_digests(self):
        for digest in [None, "bad", "0" * 64]:
            self.entry["digest"] = digest
            self.failed("bytes match original")
        self.entry["digest"] = self.digest
        self.original["entries"]["demo"].append(dict(self.entry, digest="0" * 64))
        self.failed("bytes match original")

    def exclude(self):
        self.entry["digest"] = "0" * 64
        self.excluded = [dict(self.package, reason="original_checksum_mismatch",
                              original_entries=[{"chart": "demo", "version": "1", "digest": "0" * 64}])]
        self.manifest.update(packages=[], package_count=0, excluded_package_count=1, total_bytes=0)
        self.candidate["entries"] = {}
        self.checksums = ""
        (self.root / self.path).unlink()
        self.write()

    def test_exclusion_evidence_and_absence(self):
        self.exclude()
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(verifier.main(["--root", str(self.root), "--report", str(self.root / "report.json")]), 0)
        self.assertIn("EXCLUDED", stdout.getvalue())
        (self.root / self.path).write_bytes(b"archive bytes")
        self.failed("excluded file is absent")
        (self.root / self.path).unlink()
        self.excluded[0]["original_entries"] = []
        self.failed("exclusion matches original evidence")
        self.excluded[0]["reason"] = None
        self.failed("exclusion matches original evidence")

    def test_excluded_and_retained_overlap(self):
        self.excluded = [dict(self.package, reason="not_in_original_index", original_entries=[])]
        self.failed("paths are disjoint")

    def test_historical_excluded_bytes(self):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE, text=True)
        git("init", "-b", "test")
        git("add", self.path)
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
            "commit", "--no-gpg-sign", "-m", "Synthetic archive fixture")
        commit = git("rev-parse", "HEAD").strip()
        self.exclude()
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(verifier.main(["--root", str(self.root), "--excluded-ref", commit,
                                            "--report", str(self.root / "report.json")]), 0)
        report = json.loads((self.root / "report.json").read_text())
        self.assertEqual(report["exclusions"][0]["actual_sha256"], self.digest)
        self.assertTrue(report["exclusions"][0]["bytes_rehashed"])
        self.assertIn("rehashed from Git", stdout.getvalue())
        self.assertFalse((self.root / self.path).exists())
        self.excluded[0]["size"] += 1
        self.write()
        self.assertFalse(verifier.verify(self.root, commit)["passed"])
        self.excluded[0]["sha256"] = "1" * 64
        self.write()
        self.assertFalse(verifier.verify(self.root, commit)["passed"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(verifier.main(["--root", str(self.root), "--excluded-ref", "missing-commit",
                                            "--report", str(self.root / "report.json")]), 1)

    def test_exclusion_classifier(self):
        for refs, expected in [([], "not_in_original_index"), ([{}], "missing_original_checksum"),
                               ([{"digest": "bad"}], "invalid_original_checksum"),
                               ([{"digest": self.digest}, {"digest": "0" * 64}], "conflicting_original_checksums"),
                               ([{"digest": "0" * 64}], "original_checksum_mismatch"),
                               ([{"digest": self.digest}], None)]:
            self.assertEqual(verifier.exclusion_reason(refs, self.digest), expected)

    def test_cli_failure_and_bad_inputs(self):
        (self.root / self.path).write_bytes(b"wrong")
        with redirect_stdout(io.StringIO()) as stdout:
            self.assertEqual(verifier.main(["--root", str(self.root), "--report", str(self.root / "report.json")]), 1)
        self.assertIn("FAILED:", stdout.getvalue())
        for error in [FileNotFoundError("missing yq"), ValueError("invalid JSON"), KeyError("missing entries"),
                      TypeError("wrong schema"), subprocess.CalledProcessError(1, "yq")]:
            with patch.object(verifier, "verify", side_effect=error), redirect_stdout(io.StringIO()) as stdout:
                self.assertEqual(verifier.main(["--root", str(self.root), "--report", str(self.root / "report.json")]), 1)
            self.assertIn("INPUT ERROR:", stdout.getvalue())
            self.assertFalse(json.loads((self.root / "report.json").read_text())["passed"])

    def test_cli_cannot_overwrite_inputs(self):
        for path in [self.path, "index.yaml"]:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                verifier.main(["--root", str(self.root), "--report", str(self.root / path)])
            self.assertEqual(caught.exception.code, 2)

    def test_direct_entrypoint(self):
        result = subprocess.run(["python3", str(Path(verifier.__file__)), "--root", str(self.root),
                                 "--report", str(self.root / "report.json")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
