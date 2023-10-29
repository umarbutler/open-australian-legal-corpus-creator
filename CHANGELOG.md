# Changelog
All notable changes to the Open Australian Legal Corpus Creator will be documented here. This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2023-10-30
### Fixed
- Fixed import error in the scraper for the Federal Court of Australia.

## [0.1.0] - 2023-10-29
### Added
- Created this changelog.
- Adopted [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
- Created a command-line interface for the Creator named `mkoalc`.
- Created a Python package for the Creator named `oalc_creator`.
- Introduced the `version_id` field of documents.
- Added support for the extraction of text from PDFs and DOCXs.
- Added support for documents from the [Federal Register of Legislation](https://www.legislation.gov.au/) stored as RTFs.
- Added support for documents from the [Federal Court of Australia](https://www.fedcourt.gov.au/digital-law-library/judgments/search) encoded as Windows-1252.
- Added support for documents from the [Federal Court of Australia](https://www.fedcourt.gov.au/digital-law-library/judgments/search) that were encoded incorrectly by extracting text from their DOCX versions.
- Automated the removal of incompatible Corpus data.

### Changed
- Switched from mulithreading to asyncio.
- Switched to object-oriented programming.
- Moved the `text` field of documents to the end.
- Switched to collecting documents from the [South Australian Legislation](https://www.legislation.sa.gov.au/) database by scraping it instead of using database dumps.
- Switched from updating the Corpus by redownloading all documents to updating only the documents that have changed.

### Removed
- Removed the `open_australian_legal_corpus_creator.py` creator script.
- Removed [history notes](https://legislation.nsw.gov.au/help/inlinehistorynotes) from texts.

### Fixed
- Better preserved indentation in texts.
- Reduced excessive line breaks in texts.
- Improved the extraction and cleaning of citations.

[0.1.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/releases/tag/v0.1.0