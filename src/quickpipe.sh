#for i in hard neut soft; do python FIt.py -i ${1}/${i}/pops; done
#for i in neut hard soft; do python allele_freq_mat.py ${1}/${i}/freqs; done
#python merge_npzs.py ${i}/merged_freqs.npz ${1}/*/*.npz
#python allele_freq_net.py train -i ${i}/merged_freqs.npz -n allele_freqs
python summarize_3class.py ${i} simpleAllele_freqs_1DCNN ${i}/allele_freqs_TimeSweeperHaps_predictions.csv
python plotting/plot_hap_spec.py ${i}/merged_freqs.npz
