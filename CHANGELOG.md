## Changelog 🔄
All notable changes to the Open Australian Legal Corpus Creator will be documented here. This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2024-02-17
## Fixed
- Refactored the scraper for the Federal Register of Legislation database in order to resolve breaking API changes brought about by the database's redesign, thereby fixing [#1](https://github.com/umarbutler/open-australian-legal-corpus-creator/issues/1).

## [1.0.0] - 2023-11-09
## Added
- Created a scraper for the High Court of Australia database.
- Added status code `429` as a default retryable status code.

### Changed
- Improved performance.
- Expanded the maximum number of seconds to wait between retries.
- Expanded the maximum number of seconds that can be waited between retries before raising an exception.

## [0.2.0] - 2023-11-02
### Added
- Created a scraper for the NSW Caselaw database.

### Changed
- Sped up the parsing of PDFs from the Queensland Legislation database.

## [0.1.2] - 2023-10-30
### Fixed
- Fixed a bug where everything after the first occurance of a document's abbreviated jurisdiction was stripped from its citation by switching to searching for abbreviated jurisdictions enclosed in parentheses.

## [0.1.1] - 2023-10-30
### Fixed
- Fixed import error in the scraper for the Federal Court of Australia database.

## [0.1.0] - 2023-10-29
### Added
- Created this changelog.
- Adopted Semantic Versioning.
- Created a command-line interface for the Creator named `mkoalc`.
- Created a Python package for the Creator named `oalc_creator`.
- Introduced the `version_id` field of documents.
- Added support for the extraction of text from PDFs and DOCXs.
- Added support for documents from the Federal Register of Legislation stored as RTFs.
- Added support for documents from the Federal Court of Australia encoded as Windows-1252.
- Added support for documents from the Federal Court of Australia that were encoded incorrectly by extracting text from their DOCX versions.
- Automated the removal of incompatible Corpus data.

### Changed
- Switched from mulithreading to asyncio.
- Switched to object-oriented programming.
- Moved the `text` field of documents to the end.
- Switched to collecting documents from the South Australian Legislation database by scraping it instead of using database dumps.
- Switched from updating the Corpus by redownloading all documents to updating only the documents that have changed.

### Removed
- Removed the `open_australian_legal_corpus_creator.py` creator script.
- Removed [history notes](https://legislation.nsw.gov.au/help/inlinehistorynotes) from texts.

### Fixed
- Better preserved indentation in texts.
- Reduced excessive line breaks in texts.
- Improved the extraction and cleaning of citations.

[1.0.1]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v0.1.2...v1.0.0
[0.1.2]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/releases/tag/v0.1.0