# Dependency licenses

The minimal runtime installs packages from PyPI; third-party source code is not
vendored. Retain each distribution's license notices when redistributing it.

| Package | Pinned version | License |
|---|---|---|
| beautifulsoup4 | 4.14.3 | MIT |
| feedparser | 6.0.12 | BSD-2-Clause |
| sgmllib3k | 1.0.0 | BSD |
| soupsieve | 2.9.0 | MIT |
| typing_extensions | 4.15.0 | PSF-2.0 |

This table was checked against installed distribution metadata on 2026-11-04.
Optional enrichment packages are not installed by this package and
require their own dependency/security/license review before deployment.
CI tools (build, setuptools, pip-audit, PyYAML and Gitleaks) are not runtime dependencies.
