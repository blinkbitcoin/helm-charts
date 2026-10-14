# Blink public Helm packages

This repository holds the verified public Helm release archives and index independently of the chart source repository. Archives are copied byte for byte, not rebuilt from source. Chart templates and values inside these packages intentionally remain public.

The proposed Helm repository endpoint is `https://blinkbitcoin.github.io/helm-charts/`. **It is not active until this migration is reviewed, merged, and GitHub Pages is enabled.** Existing clients should continue using `https://blinkbitcoin.github.io/charts/` until the compatibility index is updated.

```sh
helm repo add blink https://blinkbitcoin.github.io/helm-charts/
helm repo update
```

`CHECKSUMS.sha256` and `migration/manifest.json` record the copied archive bytes and their original release URLs. The original public index is preserved in `migration/original-index.yaml`.

See [MIGRATION.md](MIGRATION.md) for review gates, excluded archives, publication order, and rollback. No private source checkout or CI configuration is included in this archive.

Archives with conflicting, missing, invalid or mismatching original index checksums are excluded, as are unindexed archives. See `migration/excluded-packages.json`. No original package checksum is corrected or replaced.

## Reproduce the archive verification

The comparison script is [scripts/verify_archives.py](scripts/verify_archives.py).
It requires Python 3.11+ and [Mike Farah yq v4](https://github.com/mikefarah/yq).
Run from the repository root:

```sh
python3 scripts/verify_archives.py \
  --excluded-ref c51823cf8512ec102fee4013d93d23922f0c1684 \
  --report migration/verification-report.json > migration/verification-output.txt
cat migration/verification-output.txt
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

The verifier exits nonzero on failure. Check that exit status before relying on
the saved report. It performs no network requests and never modifies archives,
checksums or indexes.

- [Saved summary](migration/verification-output.txt): result, counts and exclusions.
- [Detailed JSON report](migration/verification-report.json): computed SHA-256 and
  size for every retained archive, original index references and digests,
  manifest and checksum-list comparisons, inventory checks and exclusion evidence.
- [Regression-test and coverage output](migration/verification-tests.txt).

The report includes hashes of the verifier and all five input metadata files to
identify the exact snapshot checked. It verifies that every retained archive
matches every original checksum, the package inventories agree, and the candidate
index preserves the retained metadata with only URLs changed. An archive is
excluded if its original checksum is missing, invalid, conflicting or does not
match, or if the archive is unindexed.

The saved run also rehashes all 12 excluded archives from the initial archive
commit, checks their recorded hashes and sizes, and compares the recorded hashes
against the original index to verify each exclusion reason. Git reads those bytes
without restoring them to `packages/`. The report records the resolved commit.
Use a full clone containing that commit; a missing commit or archive fails the run.
Without `--excluded-ref`, exclusion hashes are only previously recorded evidence,
and the report marks `bytes_rehashed: false`.

This is an offline integrity comparison against `migration/original-index.yaml`;
it does not establish release provenance, explain historical discrepancies, or
verify the future Pages endpoint.
