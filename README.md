# **Open Australian Legal Corpus Creator**

This repository is intended to preserve the code used to create the [Open Australian Legal Corpus](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus), the first and only multijurisdictional open corpus of Australian legislative and judicial documents. To download the Corpus, please visit the [HuggingFace Datasets repository](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus). Otherwise, if you are looking to replicate the Corpus, read on.

## Usage
Before collecting the Corpus, ensure that you have obtained all the necessary approvals from the sources in the Corpus to scrape their databases. Once you have such approvals, you may collect the Corpus by running the following commands:
```bash
git clone https://github.com/umarbutler/open-australian-legal-corpus-creator.git
cd open-australian-legal-corpus-creator
pip install -r requirements.txt
py open_australian_legal_corpus_creator.py
```

If the script freezes (as can often happen when using multithreading) or raises an error, you may need to run it again (it is capable of continuing from where it left off). If you continue to encounter errors, it may be that one or more websites have changed structure. This is to be expected as this codebase is not actively maintained.

Once the script has successfully completed, the Corpus should be available in `corpus.jsonl`.

## Licence
This codebase is licensed under the [MIT License](LICENCE).

## Citation
If you rely on this codebase or the Corpus, please cite:
```bibtex
@misc{butler-2023-open-australian-legal-corpus,
    author = {Butler, Umar},
    year = {2023},
    title = {Open Australian Legal Corpus},
    publisher = {Hugging Face},
    version = {3.1.0},
    doi = {10.57967/hf/1111},
    url = {https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus}
}
```
