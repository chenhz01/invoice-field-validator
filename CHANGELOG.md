# Changelog

All notable changes to this project are documented here.
Format inspired by Keep a Changelog; versions are 0.x while the tool stabilizes.

## [0.1.1] - 2026-10-13

### Changed
- Second-round revision after a full self-audit (rules 85-100 alignment pass):
  float tolerance epsilon raised 1e-9 -> 1e-6 eliminating cent-rounding false errors (3 x 19.99 case); line-amount expectation no longer pre-rounds unit_price; tax-family keys now ignored with explicit warnings; source-level test asserts zero tax rates/rules embedded

### Fixed
- Self-test suite hardened to 61 cases across three classes
  (functional / error-path / extreme-edge); final run `SUMMARY: PASS 61/61`.

## [0.1.0] - 2026-10-13

### Added
- Initial release: pure-stdlib core, argparse CLI, three-tier finding model,
  text and JSON output, and an article-level README with measured
  performance, Minimal Fallback, Design Trade-offs, Limits & Second-order
  Effects, FAQ, and Core Assumptions.
