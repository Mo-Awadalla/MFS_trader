# Research data archive

The workspace archive contains 41,044 indexed files totaling 31.28 GiB. The index records each original repository-relative path, its byte count, and its SHA-256 digest. It covers market-data inputs and full generated artifacts outside the Git import. [Checksum inventory](archive_inventory.csv)

## Reproducing a historical run

- Use the specification and source manifest in the relevant study folder. Source and result links are grouped in the [research inventory](../RESEARCH_INVENTORY.md).
- Restore matching source files under the original paths in the checksum inventory, or use the study's acquisition script with the documented dataset and time bounds. Some sources require provider access. Historical runners with recorded Windows paths require a path adjustment in a different checkout.
- The compact original manifests and reports recovered from ignored folders are under [archive_sources](archive_sources). They retain their recorded source paths.
- The Databento and Numba research dependencies are available through the microstructure extra. Both dev lockfiles include them for the corresponding offline tests.
- Saved experiments and their verification outputs describe historical simulations or feasibility screens. Reruns use a separate output directory.

The public checkout includes the research code, tests, specifications, and selected result and verification files. The bulk archive files are indexed by checksum for restoration from the original workspace or the documented source.
