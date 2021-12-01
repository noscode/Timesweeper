for i in hard neut soft; do python ../src/get_allele_freqs.py -i onepop/${i}/pops; done
for i in neut hard soft; do python ../src/allele_freq_mat.py onepop/${i}/freqs; done
python ../src/merge_npzs.py big_merged_freqs.npz onepop/*/*_freqmats.npz
python ../src/allele_freq_net.py train -i big_merged_freqs.npz -n allele_freqs
python ../src/summarize_3class.py . big_simpleAllele_freqs_1DCNN allele_freqs_TimeSweeper_predictions.csv
python ../src/plotting/plot_freq_spec.py big_merged_freqs.npz

for i in neut hard soft; do python ../src/haplotypes.py -i onepop/${i}/pops -s haps_simplesims -o onepop/${i}; done
python ../src/merge_npzs.py big_merged_haps.npz onepop/*/hfs_*.npz
python ../src/hap_networks.py train -i big_merged_haps.npz -n bighaps
python ../src/summarize_3class.py . *_predictions.csv
python ../src/plotting/plot_hap_spec.py big_merged_haps.npz
