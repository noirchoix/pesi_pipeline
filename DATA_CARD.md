# PESI-KG Data Card

## Dataset categories

- Raw source registry and normalized raw directory.
- Pathway and reaction resources.
- Kinetic resources including SKiD and SABIO cache.
- Protein/enzyme annotation resources.
- Curated enzyme-family workbooks.
- Herbicide target reference table.
- Generated outputs and artifacts.

## Provenance

The pipeline persists source table counts and records proxy-evidence status. Downstream files include evidence class columns where applicable.

## Included benchmark evidence

This package includes medium-profile outputs and artifacts sufficient for immediate API/UI inspection. Users can regenerate audit or medium outputs locally with the CLI/API run launcher.

## Sensitive data

No secrets should be committed. Plant.id and API keys must be supplied via environment variables.

## Known limitations

Data sources differ in completeness, naming conventions, and evidence depth. The pipeline uses semantic de-duplication and explicit proxy labels but cannot convert literature/database evidence into wet-lab validation.
