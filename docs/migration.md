# Staged migration and rollback

1. Keep the original production schedules and writers enabled. Record source
   counts, per-platform throughput, successful archive receipts and p50/p95 lag.
2. Validate the public package with offline fixtures and the original parsers on
   the same synthetic inputs. Review licenses, scan the candidate tree and its
   complete independent Git history, and build the release.
3. Provision a cloud runtime with a persistent disk and confirmed free quota.
   OCI Always Free is a candidate, not a provisioned or guaranteed runtime.
   Confirm home-region capacity, eligible shape, disk and traffic quota, and
   resource usage already charged to the tenancy. Do not enable paid fallback.
4. Install the pinned release in the private deployment. Preserve the approved
   registry and archive writer. Add an import adapter implementing the receipt
   contract only if using the standalone service; never open internal ports or
   create a tunnel to an internal network.
5. Seed checkpoints in a private shadow environment. Compare identities, text,
   media, timestamps, exclusions and next-page state against the old collector.
   Run recovery tests for process death, rate limit, ambiguous upload success,
   archive outage and disk pressure. Do not use a second production writer for
   shadow comparison.
6. Size the runtime with all active sources. The default service budget is only
   an example; it is not proven to sustain the complete catalog. Require no
   unexplained identity loss and no worse freshness than the old pipeline.
7. Transfer ownership for a verified source group: finish/acknowledge the old
   writer, transfer its latest checkpoint, enable the new owner, and observe
   consecutive successful imports. Keep unsupported platforms on their old path.
8. Disable only an exactly matching old schedule after its replacement has
   passed the gates. Record the old workflow ID, timer, replacement and rollback
   checkpoint. On failure, stop the new owner and resume the old one from the
   last acknowledged cursor; replay is safe only with the same canonical IDs.

Public GitHub Actions is limited here to CI, bounded offline smoke tests and
release publication. No production scheduler, private checkout, persistent loop
or private-data artifact is moved into public Actions.

As checked on 2026-11-04, standard hosted runners in public repositories are
free for permitted use. Account-specific costs and storage limits still require
verification. The free OCI resources can be unavailable or reclaimed; they do
not establish an uptime guarantee. Do not declare a zero-cost, lossless migration
until the actual account and workload have passed these gates.

References: [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[Actions limits](https://docs.github.com/en/actions/reference/limits),
[Actions terms](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions),
[OCI Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm),
[JSONBin pricing](https://jsonbin.io/pricing).
