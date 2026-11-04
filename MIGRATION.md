# Public package migration

## Plan and rationale

Preserve verified public Helm packages independently of `blinkbitcoin/charts` visibility. Serve the index and byte-identical archives from this public repository using GitHub Pages. The index uses absolute package URLs so the existing `/charts/` endpoint can serve the same index.

Retain an archive only when it is referenced by the original public index, every reference has one identical valid SHA-256 checksum, and the downloaded bytes match that checksum. Exclude the entire archive and every associated index entry if any of those conditions fail. Never choose between conflicting checksums or replace a historical checksum with a new one.

This snapshot contains 1,573 verified archives (257,796,430 bytes) and 1,573 index entries for 15 chart names. Retained archives are copied byte for byte. Retained index metadata, including original checksums, is unchanged except for package URLs.

The reproducible comparison is [scripts/verify_archives.py](scripts/verify_archives.py),
with [saved output](migration/verification-output.txt) and a
[per-archive report](migration/verification-report.json).
See [README.md](README.md#reproduce-the-archive-verification) for commands and scope.

## Excluded archives

The user's policy is to drop ambiguous archives. Twelve archives and 21 original index entries are excluded:

- Nine archives have conflicting checksums across duplicate index entries; all entries are dropped even when the current bytes match one of those checksums.
- `galoy-0.27.4.tgz` does not match its original index checksum.
- `cala-0.1.0.tgz` has no original index checksum.
- `cala-0.1.7-dev.tgz` is not referenced by the original index.

`migration/excluded-packages.json` records each exclusion, its reason, original references and observed hash. Excluded archive files are absent from the package snapshot, generated index, manifest and checksum list. `migration/original-index.yaml` remains an unchanged audit copy and is not the served root index. This PR does not delete the original GitHub release assets or rewrite Git history.

## Publication order

1. Review the verified archive manifest and exclusion report, then merge this migration.
2. Enable public GitHub Pages from `main`, root directory. `.nojekyll` keeps the site static.
3. Verify anonymous index access, every archive URL/hash, and representative `helm pull` operations.
4. Update `blinkbitcoin/charts`'s `gh-pages/index.yaml` to the verified new index so existing `/charts/` clients continue downloading. The organization currently has GitHub Team, which supports public Pages from a private repository; verify that setting again before changing visibility.
5. Verify actual CI SSH and GitHub App access, complete both producer-path checks, and have a repository administrator make `blinkbitcoin/charts` private.
6. Verify authenticated CI and anonymous package downloads after the switch.

Direct links to the old GitHub release assets, and clients using a previously cached index, will need to refresh their index or use the new URLs. Making the source repository private cannot preserve anonymous access to those old release URLs. The older `galoymoney.github.io/charts/` endpoint already returned 404 during this assessment.

## Future releases

This is a historical archive migration. It does not grant an automated publisher permission to copy new private chart content into this repository. Any future publisher must target this public package repository explicitly, publish only approved release archives, update the index, and verify checksums. Reconcile the pending private-blink release-publisher design before enabling it; it currently assumes public artifacts under the original charts repository.

## Rollback

Before source privatization, revert the compatibility index to the preserved original and leave `charts` public. Keep this package repository and its verified archives intact. After source privatization, preserve public package hosting and repair the index/CI forward; making private source public again requires a separate explicit decision. Never delete this public archive as an automatic rollback.
