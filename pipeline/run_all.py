"""
pipeline/run_all.py
====================
Master script: runs the complete CETR Index pipeline from ingestion to scoring.

Execution order:
  1. Ingest: fetch Stats Canada tables + CER generation data
  2. Clean: compute all 5 processed metric CSVs
  3. Score: compute CETR Index, sensitivity analysis, monetary valuation

Usage
-----
  python -m pipeline.run_all
  python -m pipeline.run_all --skip-ingest    # use cached data
  python -m pipeline.run_all --force-refresh  # re-download all data

Timing: ~3-5 minutes on first run (network), ~30 seconds with cached data.

Author : Ved
Updated: 2026-05-24
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from pipeline.constants import (
    DATA_INDEX, DATA_PROCESSED, DATA_RAW,
    LOG_DATE, LOG_FORMAT, PROCESSED_FILES,
)

logging.basicConfig(format=LOG_FORMAT, datefmt=LOG_DATE, level=logging.INFO)
log = logging.getLogger("run_all")


def run_ingestion(force_refresh: bool = False) -> dict:
    """Run all data ingestion scripts."""
    log.info("=" * 60)
    log.info("PHASE 1: DATA INGESTION")
    log.info("=" * 60)
    results = {}

    # Stats Canada tables
    log.info("\n[1/2] Stats Canada tables...")
    try:
        from pipeline.ingest.statcan_client import fetch_all_tables
        sc_results = fetch_all_tables(DATA_RAW, force_refresh=force_refresh)
        for name, df in sc_results.items():
            results[f"statcan_{name}"] = {"rows": len(df), "status": "ok" if len(df) > 0 else "empty"}
    except Exception as e:
        log.error("Stats Canada ingestion failed: %s", e)
        results["statcan"] = {"status": "error", "error": str(e)}

    # CER electricity data
    log.info("\n[2/2] CER electricity generation...")
    try:
        from pipeline.ingest.cer_client import fetch_all
        cer_results = fetch_all(DATA_RAW, force_refresh=force_refresh)
        for name, val in cer_results.items():
            if hasattr(val, "__len__"):
                results[f"cer_{name}"] = {"rows": len(val), "status": "ok"}
            else:
                results[f"cer_{name}"] = {"value": val, "status": "ok"}
    except Exception as e:
        log.error("CER ingestion failed: %s", e)
        results["cer"] = {"status": "error", "error": str(e)}

    return results


def run_cleaning() -> dict:
    """Run all five metric cleaning scripts."""
    log.info("\n" + "=" * 60)
    log.info("PHASE 2: DATA CLEANING")
    log.info("=" * 60)
    results = {}

    cleaners = [
        ("carbon_intensity",    "pipeline.clean.carbon_intensity"),
        ("stranded_asset_risk", "pipeline.clean.stranded_asset_risk"),
        ("workforce_exposure",  "pipeline.clean.workforce_exposure"),
        ("energy_poverty",      "pipeline.clean.energy_poverty"),
        ("grid_reliability",    "pipeline.clean.grid_reliability"),
    ]

    for i, (name, module_path) in enumerate(cleaners, 1):
        log.info("\n[%d/%d] %s...", i, len(cleaners), name)
        try:
            import importlib
            module = importlib.import_module(module_path)
            df = module.compute()
            rows = len(df) if df is not None else 0
            results[name] = {"rows": rows, "status": "ok"}
            log.info("  ✓ %d rows", rows)
        except Exception as e:
            log.error("  ✗ %s failed: %s", name, e)
            results[name] = {"status": "error", "error": str(e)}

    return results


def run_scoring() -> dict:
    """Run the index calculator and sensitivity analysis."""
    log.info("\n" + "=" * 60)
    log.info("PHASE 3: SCORING")
    log.info("=" * 60)
    results = {}

    log.info("\n[1/1] Computing CETR Index (all years)...")
    try:
        from pipeline.score.index_calculator import run_all_years
        df = run_all_years()
        rows = len(df) if df is not None else 0
        years = df["year"].nunique() if df is not None and "year" in df.columns else 0
        results["index"] = {"rows": rows, "years": years, "status": "ok"}
    except Exception as e:
        log.error("  ✗ Index calculation failed: %s", e)
        results["index"] = {"status": "error", "error": str(e)}

    return results


def write_run_log(results: dict, elapsed: float) -> None:
    """Write run summary to data/index/run_log.json."""
    DATA_INDEX.mkdir(parents=True, exist_ok=True)
    log_path = DATA_INDEX / "run_log.json"

    existing = []
    if log_path.exists():
        try:
            with open(log_path) as f:
                existing = json.load(f)
        except Exception:
            existing = []

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "results": results,
    }
    existing.append(entry)

    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2)
    log.info("Run log updated: %s", log_path.name)


def main():
    parser = argparse.ArgumentParser(description="Run the full CETR Index pipeline.")
    parser.add_argument("--skip-ingest", action="store_true",
                        help="Skip data ingestion (use cached raw data)")
    parser.add_argument("--force-refresh", action="store_true",
                        help="Force re-download of all data")
    parser.add_argument("--phase", choices=["ingest", "clean", "score", "all"],
                        default="all", help="Run only a specific phase")
    args = parser.parse_args()

    # Ensure data directories exist
    for d in [DATA_RAW, DATA_PROCESSED, DATA_INDEX]:
        d.mkdir(parents=True, exist_ok=True)

    start_time = time.time()
    all_results = {}

    log.info("╔══════════════════════════════════════════╗")
    log.info("║     CETR Index Pipeline — Starting       ║")
    log.info("╚══════════════════════════════════════════╝")
    log.info("Timestamp: %s", datetime.utcnow().isoformat())

    # Phase 1: Ingestion
    if not args.skip_ingest and args.phase in ("ingest", "all"):
        ingest_results = run_ingestion(force_refresh=args.force_refresh)
        all_results["ingestion"] = ingest_results
        ingest_errors = [k for k, v in ingest_results.items() if v.get("status") == "error"]
        if ingest_errors:
            log.warning("Ingestion errors (continuing with fallback data): %s", ingest_errors)

    # Phase 2: Cleaning
    if args.phase in ("clean", "all"):
        clean_results = run_cleaning()
        all_results["cleaning"] = clean_results
        clean_errors = [k for k, v in clean_results.items() if v.get("status") == "error"]
        if clean_errors:
            log.error("Cleaning errors: %s", clean_errors)
            log.error("Cannot proceed to scoring with missing metrics.")
            sys.exit(1)

    # Phase 3: Scoring
    if args.phase in ("score", "all"):
        score_results = run_scoring()
        all_results["scoring"] = score_results
        if score_results.get("index", {}).get("status") == "error":
            log.error("Scoring failed.")
            sys.exit(1)

    # Summary
    elapsed = time.time() - start_time
    write_run_log(all_results, elapsed)

    log.info("\n╔══════════════════════════════════════════╗")
    log.info("║         Pipeline Complete ✓              ║")
    log.info("╚══════════════════════════════════════════╝")
    log.info("Elapsed: %.1f seconds", elapsed)
    log.info("Outputs:")
    from pipeline.constants import INDEX_FILES
    for name, path in INDEX_FILES.items():
        exists = "✓" if path.exists() else "✗ MISSING"
        log.info("  %s %s", exists, path)


if __name__ == "__main__":
    main()
