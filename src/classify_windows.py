import argparse as ap
import os

import allel
import numpy as np
import pandas as pd
import yaml
from tensorflow.keras.models import load_model
from tqdm import tqdm

from frequency_increment_test import fit
from utils import hap_utils as hu, snp_utils as su


def prep_ts_afs(genos, samp_sizes):
    # Prep genos into time-series format and calculate MAFs
    ts_genos = su.split_arr(genos, samp_sizes)
    min_alleles = su.get_minor_alleles(ts_genos)

    ts_mafs = []
    for timepoint in ts_genos:
        _genos = []
        _genotypes = allel.GenotypeArray(timepoint).count_alleles()
        for snp, min_allele_idx in zip(_genotypes, min_alleles):
            maf = su.calc_mafs(snp, min_allele_idx)
            _genos.append(maf)

        ts_mafs.append(_genos)

    # Shape is (timepoints, MAF)
    return np.stack(ts_mafs)


def run_afs_windows(snps, genos, samp_sizes, win_size, model):
    ts_afs = prep_ts_afs(genos, samp_sizes)

    # Iterate over SNP windows and predict
    results_dict = {}
    buffer = int(win_size / 2)
    centers = range(buffer, len(snps) - buffer)
    for center in tqdm(centers, desc="Predicting on AFS windows"):
        win_idxs = get_window_idxs(center, win_size)
        window = ts_afs[:, win_idxs]

        # For plotting
        if snps[center][2] == 2 or center == int(len(centers) / 2):
            center_afs = window

        probs = model.predict(np.expand_dims(window, 0))
        results_dict[snps[center]] = probs

    return results_dict, center_afs


def run_fit_windows(snps, genos, samp_sizes, win_size, gens):
    ts_afs = prep_ts_afs(genos, samp_sizes)
    results_dict = {}
    buffer = int(win_size / 2)
    for idx in tqdm(range(buffer, len(snps) - buffer), desc="Calculating FIT values"):
        results_dict[snps[idx]] = fit(list(ts_afs[:, idx]), gens)  # tval, pval

    return results_dict


def run_hfs_windows(snps, haps, samp_sizes, win_size, model):
    results_dict = {}
    buffer = int(win_size / 2)
    centers = range(buffer, len(snps) - buffer)
    for center in tqdm(centers, desc="Predicting on HFS windows"):
        win_idxs = get_window_idxs(center, win_size)
        window = np.swapaxes(haps[win_idxs, :], 0, 1)
        str_window = hu.haps_to_strlist(window)
        hfs = hu.getTSHapFreqs(str_window, samp_sizes)

        # For plotting
        if snps[center][2] == 2 or center == int(len(centers) / 2):
            center_hfs = hfs

        win_idxs = get_window_idxs(center, win_size)
        window = np.swapaxes(haps[win_idxs, :], 0, 1)
        str_window = hu.haps_to_strlist(window)
        # For plotting
        probs = model.predict(np.expand_dims(hfs, 0))
        results_dict[snps[center]] = probs

    return results_dict, center_hfs


def classify_window(win_snps, model):
    return model.predict(win_snps)


def get_window_idxs(center_idx, win_size):
    half_window = int(win_size / 2)
    return list(range(center_idx - half_window, center_idx + half_window + 1))


def load_nn(model_path, summary=False):
    model = load_model(model_path)
    if summary:
        print(model.summary())

    return model


def write_fit(fit_dict, outfile):
    chroms, bps, mut_type = zip(*fit_dict.keys())

    inv_pval = [1 - i[1] for i in fit_dict.values()]

    predictions = pd.DataFrame(
        {"Chrom": chroms, "BP": bps, "Mut Type": mut_type, "Inv pval": inv_pval}
    )
    predictions.sort_values(["Chrom", "BP"], inplace=True)

    predictions.to_csv(os.path.join(outfile), header=True, index=False, sep="\t")


def write_preds(results_dict, outfile):
    lab_dict = {0: "Neut", 1: "Hard", 2: "Soft"}
    chroms, bps, mut_type = zip(*results_dict.keys())

    neut_scores = [i[0][0] for i in results_dict.values()]
    hard_scores = [i[0][1] for i in results_dict.values()]
    soft_scores = [i[0][2] for i in results_dict.values()]

    classes = [lab_dict[np.argmax(i, axis=1)[0]] for i in results_dict.values()]
    predictions = pd.DataFrame(
        {
            "Chrom": chroms,
            "BP": bps,
            "Mut Type": mut_type,
            "Class": classes,
            "Neut Score": neut_scores,
            "Hard Score": hard_scores,
            "Soft Score": soft_scores,
        }
    )
    predictions.sort_values(["Chrom", "BP"], inplace=True)

    predictions.to_csv(os.path.join(outfile), header=True, index=False, sep="\t")


def add_file_label(filename, label):
    splitfile = filename.split(".")
    newname = f"{''.join(splitfile[:-1])}_{label}.{splitfile[-1]}"
    return newname


def parse_ua():
    uap = ap.ArgumentParser(
        description="Module for iterating across windows in a time-series vcf file and predicting whether a sweep is present at each snp-centralized window."
    )
    subparsers = uap.add_subparsers(dest="format")
    subparsers.required = True
    yaml_parser = subparsers.add_parser("yaml")
    yaml_parser.add_argument(
        "-y",
        "--yaml",
        metavar="YAML CONFIG",
        dest="yaml_file",
        help="YAML config file with all cli options defined.",
    )

    cli_parser = subparsers.add_parser("cli")
    cli_parser.add_argument(
        "-i",
        "--input-vcf",
        dest="input_vcf",
        help="Merged VCF to scan for sweeps. Must be merged VCF where files are merged in order from earliest to latest sampling time, -0 flag must be used.",
        required=True,
    )

    cli_parser.add_argument(
        "-s",
        "--sample-sizes",
        dest="samp_sizes",
        help="Number of individuals from each timepoint sampled. Used to index VCF data from earliest to latest sampling points.",
        required=True,
        nargs="+",
        type=int,
    )

    cli_parser.add_argument(
        "-p",
        "--ploidy",
        dest="ploidy",
        help="Ploidy of organism being sampled.",
        default="2",
        type=int,
    )

    cli_parser.add_argument(
        "--afs-model",
        dest="afs_model",
        help="Path to Keras2-style saved model to load for AFS prediction.",
        required=True,
    )
    cli_parser.add_argument(
        "--hfs-model",
        dest="hfs_model",
        help="Path to Keras2-style saved model to load for HFS prediction.",
        required=True,
    )
    cli_parser.add_argument(
        "-o",
        "--output-dir",
        dest="outfile",
        help="Prefix directory to write results to.",
        required=False,
        default="Timesweeper_predictions.csv",
    )
    return uap.parse_args()


def read_config(yaml_file):
    with open(yaml_file, "r") as infile:
        yamldata = yaml.safe_load(infile)

    return yamldata


def main():
    ua = parse_ua()
    if ua.format == "yaml":
        yaml_data = read_config(ua.yaml_file)
        (
            input_vcf,
            samp_sizes,
            ploidy,
            outfile,
            afs_model_path,
            hfs_model_path,
        ) = yaml_data.values()
    elif ua.format == "cli":
        input_vcf, samp_sizes, ploidy, outfile, afs_model, hfs_model = (
            ua.input_vcf,
            ua.samp_sizes,
            ua.ploidy,
            ua.outfile,
            load_nn(ua.afs_model),
            load_nn(ua.hfs_model),
        )

    win_size = 51  # Must be consistent with training data

    indir = os.path.dirname(input_vcf)

    # AFS
    genos, snps = su.vcf_to_genos(input_vcf)
    afs_predictions, central_afs = run_afs_windows(
        snps, genos, samp_sizes, win_size, afs_model
    )

    # afs_file = add_file_label(input_vcf, "afs")
    write_preds(afs_predictions, f"{indir}/afs_preds.csv")

    # HFS
    haps, snps = su.vcf_to_haps(input_vcf)
    hfs_predictions, central_hfs = run_hfs_windows(
        snps, haps, [ploidy * i for i in samp_sizes], win_size, hfs_model
    )
    # hfs_file = add_file_label(input_vcf, "hfs")
    write_preds(hfs_predictions, f"{indir}/hfs_preds.csv")

    # FIT
    GEN_STEP = 10
    GENS = list(range(10060, 10250 + GEN_STEP, GEN_STEP))
    genos, snps = su.vcf_to_genos(input_vcf)
    fit_predictions = run_fit_windows(snps, genos, samp_sizes, win_size, GENS)
    # fit_file = add_file_label(input_vcf, "fit")
    write_fit(fit_predictions, f"{indir}/fit_preds.csv")

    np.save(os.path.join(indir, "afs_centers.npy"), central_afs)
    np.save(os.path.join(indir, "hfs_centers.npy"), central_hfs)


""" 
Example Usage

python classify_windows.py \
    -nn ../simple_sims/models/bighaps_TimeSweeper \
    -i ../simple_sims/vcf_sims/hard/pops/1/merged.vcf.gz \
    -s $(printf '10 %.s' {1..20})

"""

if __name__ == "__main__":
    main()
