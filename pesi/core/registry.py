from __future__ import annotations

import json
import shutil
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .utils import ensure_dir, file_size, sha256_file, write_json


@dataclass
class ResourceSpec:
    key: str
    filename: str
    normalized_dir: str
    layer: str
    aims: str
    role: str
    license_note: str
    importance: str
    optional: bool = False


RESOURCE_SPECS: list[ResourceSpec] = [
    ResourceSpec("plantcyc", "20640438.zip", "plantcyc", "Layer 1", "Aim 1/Aim 2/Aim 3", "Plant metabolism and pathway RDF", "Check PlantCyc/MetaCyc license terms before redistribution", "★★★★★"),
    ResourceSpec("cazy", "cazy_data.zip", "cazy", "Layer 1", "Aim 1/Aim 2/Aim 3", "Carbohydrate-active enzyme families relevant to germination/cell wall metabolism", "CAZy data terms apply; cite CAZy", "★★★★★"),
    ResourceSpec("bkms", "Reactions_BKMS.tar.gz", "bkms", "Layer 2", "Aim 1/Aim 2/Aim 3", "Reaction network and EC/reaction/pathway identifiers", "Respect BKMS source terms and cite", "★★★★★"),
    ResourceSpec("plantmetwiki", "fulldata_release.zip", "plantmetwiki", "Layer 1/Layer 5", "Aim 1/Aim 2", "Plant metabolism graph, splits and embeddings", "Use according to bundled LICENSE/provenance", "★★★★★"),
    ResourceSpec("enzyme_datasets", "enzyme-datasets-main.zip", "enzyme_datasets", "Layer 5", "Aim 2/Aim 4", "Supervised enzyme ML benchmark datasets", "Repository license applies", "★★★★★"),
    ResourceSpec("enzymeflow", "EnzymeFlow-main.zip", "enzymeflow", "Layer 4/Layer 5", "Aim 2/Aim 3", "Protein/pocket representation and structural model assets", "Repository license applies", "★★★★☆"),
    ResourceSpec("reactzyme", "ReactZyme-main.zip", "reactzyme", "Layer 2/Layer 5", "Aim 2/Aim 3", "Reaction prediction codebase and compatible schema", "Repository license applies", "★★★★☆"),
    ResourceSpec("skid_repo", "SKiD-main.zip", "skid_repo", "Layer 3/Layer 4", "Aim 1/Aim 3", "Structure-oriented kinetics methodology/code assets", "TCS/SKiD academic/noncommercial conditions apply", "★★★★★"),
    ResourceSpec("enzyme_smi", "enzyme_smi_split.zip", "enzyme_smi", "Layer 4/Layer 5", "Aim 4", "Protein-sequence/SMILES positive interactions", "Dataset license unknown from archive; verify before redistribution", "★★★★★"),
    ResourceSpec("fooddb", "food_chemistry.zip", "fooddb", "Layer 1/Layer 4", "Aim 1/Aim 4", "FoodDB-derived natural compound/source/enzyme/pathway edges", "FoodDB/curation license terms apply", "★★★★★"),
    ResourceSpec("skid_main", "Main_dataset_v1.xlsx", "skid", "Layer 3/Layer 4/Layer 5", "Aim 1/Aim 3", "SKiD main kcat/Km/unique enzyme/substrate workbook", "TCS/SKiD academic/noncommercial conditions apply", "★★★★★"),
    ResourceSpec("skid_paper", "skid.pdf", "docs", "Layer 3/Layer 4", "Aim 1/Aim 3", "SKiD methodology paper", "bioRxiv/CC-BY-NC-ND / preprint terms apply", "★★★★★"),
    ResourceSpec("uniprot_rhea", "cleaned_uniprot_rhea.tsv", "uniprot_rhea", "Layer 2", "Aim 1/Aim 2/Aim 3", "Canonical UniProt to Rhea/EC/sequence mapping", "UniProt/Rhea terms apply", "★★★★★"),
    ResourceSpec("molecule_vocab", "molecule_vocab.pkl", "vocabs", "Layer 4", "Aim 4", "Molecule vocabulary asset", "Unknown; verify original source", "★★★★☆"),
    ResourceSpec("deepchem_vocab", "deepchem_vocab.txt", "vocabs", "Layer 4", "Aim 4", "SMILES/token vocabulary", "Unknown; verify original source", "★★★★☆"),
    ResourceSpec("weed_assignment", "Enzymology assignmenttt[1].docx", "docs", "Layer 1", "Aim 2/Aim 3", "Manual weed enzyme-control anchors and known herbicide targets", "User-authored/educational document", "★★★★★"),
    ResourceSpec("marangoni_kinetics", "309_Enzyme Kinetics.pdf", "docs", "Layer 3", "Aim 3/Aim 4", "Kinetic modeling principles", "Copyrighted textbook; do not redistribute beyond user-provided artifact", "★★★★★"),
    ResourceSpec("copeland_enzymes", "enzymes-a-practical-guide2.pdf", "docs", "Layer 3", "Aim 3/Aim 4", "Inhibition, ligand binding, assay design and data analysis", "Copyrighted textbook; do not redistribute beyond user-provided artifact", "★★★★★"),
    ResourceSpec("enzyme_design_review", "D3025043414.pdf", "docs", "Layer 4", "Aim 2/Aim 3/Future Work", "Computational enzyme design overview", "Publisher/license terms apply", "★★★☆☆"),
    ResourceSpec("kiss_enzyme_design", "Kiss_AngewChemIntEd_2013.pdf", "docs", "Layer 4", "Future Work", "Computational enzyme design review and limitations", "Publisher/license terms apply", "★★★★☆"),
    ResourceSpec("computational_enzymology", "192570_Chapter_4_PrintPDF.pdf", "docs", "Layer 4", "Aim 3/Future Work", "QM/MM, MD and mechanistic modeling guidance", "Publisher/license terms apply", "★★★★☆"),
]

CURATED_FAMILY_FILES = [
    "Aminotransferase_Minimally_Curated_Set.xlsx",
    "BAHD_acyltransferase_Minimally_Curated_Set.xlsx",
    "Cytochrome_P450_Minimally_Curated_Set.xlsx",
    "Dioxygenase_Minimally_Curated_Set.xlsx",
    "GDSL_lipase_esterase_Minimally_Curated_Set.xlsx",
    "Methyltransferase_Minimally_Curated_Set.xlsx",
    "Peroxidase_Minimally_Curated_Set.xlsx",
    "Polyketide_synthase_Minimally_Curated_Set.xlsx",
    "UDP_glycosyltransferase_Minimally_Curated_Set.xlsx",
]


def _copy_file(src: Path, dest: Path, force: bool = False) -> None:
    ensure_dir(dest.parent)
    if force and dest.exists():
        dest.unlink()
    if not dest.exists():
        shutil.copy2(src, dest)


def _extract_zip(src: Path, dest: Path, force: bool = False) -> None:
    ensure_dir(dest)
    marker = dest / ".extracted_from"
    if force and dest.exists():
        shutil.rmtree(dest)
        ensure_dir(dest)
    if marker.exists() and not force:
        return
    with zipfile.ZipFile(src) as z:
        z.extractall(dest)
    marker.write_text(src.name, encoding="utf-8")


def _extract_tar(src: Path, dest: Path, force: bool = False) -> None:
    ensure_dir(dest)
    marker = dest / ".extracted_from"
    if force and dest.exists():
        shutil.rmtree(dest)
        ensure_dir(dest)
    if marker.exists() and not force:
        return
    with tarfile.open(src, "r:*") as t:
        t.extractall(dest)
    marker.write_text(src.name, encoding="utf-8")


def bootstrap_raw(source_dir: str | Path, raw_dir: str | Path, force: bool = False) -> pd.DataFrame:
    source = Path(source_dir)
    raw = ensure_dir(raw_dir)
    ensure_dir(raw / "archives")
    records: list[dict[str, Any]] = []

    for spec in RESOURCE_SPECS:
        src = source / spec.filename
        status = "missing"
        dest_hint = ""
        err = ""
        if src.exists():
            try:
                # preserve a copy of every source artifact in raw/archives or normalized docs/files.
                if spec.filename.endswith((".zip", ".tar.gz", ".tgz")):
                    _copy_file(src, raw / "archives" / spec.filename, force=force)
                    if spec.filename.endswith(".zip"):
                        _extract_zip(src, raw / spec.normalized_dir, force=force)
                    else:
                        _extract_tar(src, raw / spec.normalized_dir, force=force)
                    dest_hint = str(raw / spec.normalized_dir)
                elif spec.key.startswith("skid") and spec.filename.endswith(".xlsx"):
                    _copy_file(src, raw / "skid" / spec.filename, force=force)
                    dest_hint = str(raw / "skid" / spec.filename)
                elif spec.key == "uniprot_rhea":
                    _copy_file(src, raw / "uniprot_rhea" / spec.filename, force=force)
                    dest_hint = str(raw / "uniprot_rhea" / spec.filename)
                elif spec.key in {"molecule_vocab", "deepchem_vocab"}:
                    _copy_file(src, raw / "vocabs" / spec.filename, force=force)
                    dest_hint = str(raw / "vocabs" / spec.filename)
                elif spec.normalized_dir == "docs":
                    _copy_file(src, raw / "docs" / spec.filename, force=force)
                    dest_hint = str(raw / "docs" / spec.filename)
                else:
                    _copy_file(src, raw / spec.normalized_dir / spec.filename, force=force)
                    dest_hint = str(raw / spec.normalized_dir / spec.filename)
                status = "bootstrapped"
            except Exception as e:
                status = "error"
                err = repr(e)
        records.append({
            **asdict(spec),
            "source_path": str(src),
            "source_exists": src.exists(),
            "source_size_bytes": file_size(src) if src.exists() else 0,
            "source_sha256": sha256_file(src) if src.exists() and file_size(src) < 600_000_000 else "skipped_large_or_missing",
            "normalized_path": dest_hint,
            "bootstrap_status": status,
            "error": err,
        })

    cf_dir = ensure_dir(raw / "curated_families")
    for filename in CURATED_FAMILY_FILES:
        src = source / filename
        status = "missing"
        err = ""
        dest = cf_dir / filename
        if src.exists():
            try:
                _copy_file(src, dest, force=force)
                status = "bootstrapped"
            except Exception as e:
                status = "error"; err = repr(e)
        records.append({
            "key": f"curated_{filename.replace('.xlsx','')}",
            "filename": filename,
            "normalized_dir": "curated_families",
            "layer": "Layer 5",
            "aims": "Aim 2/Aim 3/Aim 4",
            "role": "Gold-standard enzyme family label workbook",
            "license_note": "User-provided minimally curated enzyme family workbook; verify upstream sources for publication",
            "importance": "★★★★★",
            "optional": False,
            "source_path": str(src),
            "source_exists": src.exists(),
            "source_size_bytes": file_size(src) if src.exists() else 0,
            "source_sha256": sha256_file(src) if src.exists() else "missing",
            "normalized_path": str(dest) if src.exists() else "",
            "bootstrap_status": status,
            "error": err,
        })

    df = pd.DataFrame(records)
    ensure_dir(raw / "_registry")
    df.to_csv(raw / "_registry" / "resource_registry_bootstrap.csv", index=False)
    write_json(raw / "_registry" / "resource_registry_bootstrap.json", df.to_dict("records"))
    return df


def base_registry(raw_dir: str | Path) -> pd.DataFrame:
    p = Path(raw_dir) / "_registry" / "resource_registry_bootstrap.csv"
    if p.exists():
        return pd.read_csv(p)
    # Minimal expected registry without bootstrap.
    return pd.DataFrame([asdict(s) for s in RESOURCE_SPECS])
