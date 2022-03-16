import allel
import numpy as np
import re

# General util functions
def read_vcf(vcf_file, benchmark, region=None):
    """
    Loads VCF file and grabs relevant fields.

    Args:
        vcf_file (str): Path to vcf file.
        benchmark (bool): Whether to look for mut type or not.
        region (str): Contig label in VCF if subsetting.
    Returns:
        allel.vcf object: VCF data in the form of dictionary type object.
    """
    if benchmark:
        fields = ["variants/CHROM", "variants/POS", "calldata/GT", "variants/MT"]
    else:
        fields = ["variants/CHROM", "variants/POS", "calldata/GT"]

    if region:
        vcf = allel.read_vcf(vcf_file, fields=fields, region=region)
    else:
        vcf = allel.read_vcf(vcf_file, fields=fields)

    return vcf


def get_vcf_iter(vcf_file, benchmark, region=None):
    """
    Loads VCF file into allel generator and grabs relevant fields.

    Args:
        vcf_file (str): Path to vcf file.
        benchmark (bool): Whether to look for mut type or not.

    Returns:
        allel.vcf_iterator object: Generator for VCF data in the form of dictionary type object.
    """
    if benchmark:
        fields = ["variants/CHROM", "variants/POS", "calldata/GT", "variants/MT"]
    else:
        fields = ["variants/CHROM", "variants/POS", "calldata/GT"]

    if region:
        vcf_iter = allel.iter_vcf_chunks(vcf_file, fields=fields, region=region)
    else:
        vcf_iter = allel.iter_vcf_chunks(vcf_file, fields=fields)

    return vcf_iter


def get_vcf_contigs(vcf_file):
    """Returns sanitized contig IDs from VCF for chunked processing."""
    raw_header = allel.read_vcf_headers(vcf_file)[0]
    contig_ids = [i for i in raw_header if "contig" in i]
    clean_contigs = [re.findall("\d+", contig)[0] for contig in contig_ids]

    return clean_contigs


def get_geno_arr(vcf):
    """
    Returns Genotype array with calldata.

    Args:
        vcf (allel.vcf object): VCF dict-like object.

    Returns:
        allel.GenotypeArray: Genotype data in the form of np-like array.
    """
    return allel.GenotypeArray(vcf["calldata/GT"])


def make_loc_tups(vcf, benchmark):
    """
    Zips up chrom, position, and mutations for easy dict-filling.

    Args:
        vcf (allel.vcf object): VCF dict-like object.
        benchmark (bool): Whether to look for mut type or not.

    Returns:
        list[tuple]: List of tuples with (chrom, pos, mut).
    """
    if benchmark:
        return list(zip(vcf["variants/CHROM"], vcf["variants/POS"], vcf["variants/MT"]))
    else:
        return list(zip(vcf["variants/CHROM"], vcf["variants/POS"]))


### Get afs from vcf
def vcf_to_genos(vcf_file, benchmark, contig=None):
    """
    Takes in vcf file, accesses and collates data for easy genotype dict-filling.

    Args:
        vcf_file (str): Path to vcf file.
        benchmark (bool): Whether to look for mut type or not.

    Returns:
        tuple[allel.GenotypeArray, list[tup(chrom, pos,  mut)]]: Genotype arrays and associated id information.
    """
    vcf = read_vcf(vcf_file, benchmark, contig)
    geno_arr = get_geno_arr(vcf)
    locs = make_loc_tups(vcf, benchmark)

    return geno_arr, locs


### Haplotypes from VCF
def vcf_to_haps(vcf_file, benchmark, contig=None):
    """
    Takes in vcf file, accesses and collates data for easy haplotype dict-filling.

    Args:
        vcf_file (str): Path to vcf file.
        benchmark (bool): Whether to look for mut type or not.

    Returns:
        tuple[allel.HaplotypeArray, list[tup(chrom, pos,  mut)]]: Haplotype arrays and associated id information.
    """
    vcf = read_vcf(vcf_file, benchmark, contig)
    hap_arr = get_geno_arr(vcf).to_haplotypes()
    locs = make_loc_tups(vcf, benchmark)

    return hap_arr, locs


def split_arr(arr, samp_sizes):
    """
    Restacks array to be in list of shape (timepoint_bins[snps, inds, alleles]).

    Args:
        arr (np.arr): SNP or Haplotype array with all timepoints in flat structure.
        samp_sizes (list(int)): List of chromosomes (not individuals) to index from the array.

    Returns:
        list[np.arr]: Time-serialized list of arrays of SNP or haplotype data.
    """
    # print(arr.shape)
    i = 0
    arr_list = []
    for j in samp_sizes:
        arr_list.append(arr[:, i : i + j, :])
        i += j

    # print(np.stack(arr_list).shape)
    return arr_list


def get_minor_alleles(ts_genos):
    """
    Gets index of minor allele to use for MAF.
    Based on the highest-frequency minor allele at last timepoint.

    Args:
        ts_genos (np.arr): Time-series array of SNPs organized with split_arr().

    Returns:
        np.arr: Array of indices of minor alleles.
    """
    # Shape is (snps, counts)
    # Use allele that is highest freq at final timepoint
    last_genos = allel.GenotypeArray(ts_genos[-1]).count_alleles()

    return np.argmax(last_genos[:, 1:], axis=1) + 1


def calc_mafs(snp, min_allele_idx):
    """
    Calculates minor allele frequency for given snp.

    Args:
        snp (np.arr): Frequencies of all minor alleles for a given SNP.
        min_allele_idx (int): Index of minor allele at highest frequency at final timepoint.

    Returns:
        float: Minor allele frequency (MAF) at a given timepoint.
    """
    return snp[min_allele_idx] / snp.sum()
