# Naming and Package Availability

Date checked: 2026-06-14.

## Python package name

The PyPI package name `midas` is already taken by another project. MIDAS therefore
uses the distribution name `midas-agent` while keeping the command-line entry point
as `midas`.

Current packaging decision:

- PyPI distribution: `midas-agent`
- CLI command: `midas`
- Product/brand wording: `MIDAS` or `MIDAS Agent`

## Availability checks

Checks performed:

- `https://pypi.org/project/midas/` returned an active package.
- `https://pypi.org/pypi/midas/json` returned HTTP 200.
- `https://pypi.org/pypi/midas-agent/json` returned HTTP 404 at check time.
- `https://pypi.org/pypi/midas-operator/json` returned HTTP 404 at check time.

HTTP 404 on PyPI means the name was not published at that moment. It does not reserve
the name, and it does not prove trademark clearance.

## Trademark/legal note

`MIDAS` is a common term and is used by many unrelated products. Before a serious public
launch, run a proper trademark and domain review in the target countries and categories.
This repository does not claim affiliation with any other MIDAS product or project.

Avoid legal overclaims in public copy. Say what the project does; do not claim it is
certified, compliant, guaranteed, or risk-free unless that has been independently proven.
