# Public package migration

## Plan and rationale

Preserve the existing public Helm archive independently of `blinkbitcoin/charts` visibility. Serve the index and byte-identical archives from this public repository using GitHub Pages. Relative artifact layout is `packages/<release-tag>/<filename>`; the index uses absolute URLs so the old `/charts/` index can point at the same files.

This snapshot includes 1,585 release archives (258,606,007 bytes), including one archive not referenced by the existing index. The index retains all 1,594 entries for 15 chart names. Package metadata is preserved except for archive URLs and the checksum corrections recorded below.

## Integrity review required

The current public index contains duplicate URLs with conflicting checksums, one entry without a checksum, and one release whose bytes match none of its indexed checksums. `migration/checksum-discrepancies.json` lists every changed checksum. The candidate index records the SHA-256 of the actual published archive bytes. The original index is retained unchanged for comparison.

The material single-entry discrepancy is `galoy-0.27.4.tgz`:

- Original index: `878b824ba4396f33fa59e2e3858bbea379aa7ba7842d1f49f5fbc78072d4efa9`
- Current public release bytes: `07c5cd903e543c416a6656fe182263411da1d645e2fc2f77930721c421168850`
- Archive metadata: chart `galoy`, version `0.27.4`, appVersion `0.16.84`.

The investigation does not establish why these historical checksums differ. Review the decision to preserve currently published bytes and correct the index before merging. Do not treat the changed checksum as proof of historical provenance.

## Publication order

1. Review the archive manifest and checksum corrections, then merge this migration.
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
