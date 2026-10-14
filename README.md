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
