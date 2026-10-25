# CloudNativePG CRDs (`crds/cnpg/`)

| File | Description |
| :--- | :--- |
| [crds.yaml](crds.yaml) | The 9 CloudNativePG CRDs, split out of the upstream release manifest. The operator itself is in [../../operators/cnpg/operator.yaml](../../operators/cnpg/operator.yaml). |

When upgrading CNPG, regenerate both files from the same upstream release: the CRD documents go here, everything else into `operators/cnpg/operator.yaml`. Renovate is disabled for both.
