## Changelog 🔄
All notable changes to the Open Australian Legal Corpus Creator will be documented here. This project adheres to [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2024-06-01
### Added
- Added the `date` field.
- Added the `mime` field for storing the original MIME type of documents.
- Began lightly cleaning texts.
- Introduced the `max_concurrent_ocr` argument to `Creator` and `-m`/`--max-concurrent-ocr` argument to `mkoalc` to limit the maximum number of PDFs that may be OCR'd concurrently.

### Changed
- Suffixed the ids of documents in the Western Australian legislation database with their version ids, delimited by a slash, in order to make it easier to track changes to documents.
- Started filtering out documents with texts that, after being cleaned and stripped of non-alphabetic characters, are less than 9 characters long.
- Replaced PDF text extraction via `pdfplumber` with OCR via `tesseract` and `tesserocr` as most PDFs were poorly OCR'd.

### Fixed
- Improved removal of empty and restricted decisions from the NSW Caselaw database by making existing keyword searches for 'Decision number not in use' and 'Decision restricted' case- and whitespace-insensitive.
- Fixed documents from the Western Australian legislation database never being updated due to the use of the last modified date of the status pages of documents as version ids when the last modified date remained constant for all pages by switching to use the XXH3 64-bit hexidecimal hash of the `main` element of the status pages as version ids.
- Fixed bug preventing the scraping of documents from the Tasmanian Legislation database due to the improper skipping of documents that contain the substring 'Content Not Found.' and also set the substring to skip on to 'Content Not Found' (without a period, as it is not used by the database).
- Ensured that warnings are raised when the only version of a document available from the Federal Register of Legislation is a DOC.
- Fixed a bug preventing the scraping of PDFs from the Federal Register of Legislation database.
- Fixed a bug causing roughly 5.3k documents to be missed from the Federal Register of Legislation database during indexing as a result of a likely bug in the database.

### Removed
- Removed unused `dict2inst` helper function that converted dictionaries to instances of classes.

## [2.0.0] - 2024-05-18
### Added
- Introduced the `when_scraped` field of documents.
- Started retrying requests when parsing errors are encountered to cope with servers being overloaded but returning successful status codes.
- Added support for Python 3.10 and 3.11.
- Began checking for and removing corrupted documents from the Corpus.

### Changed
- Switched from `attrs` and `orjson` to `msgspec` in order to speed up and simplify the serialisation and deserialisation of Corpus data.
- Reduced the semaphore limit for the NSW Caselaw and Federal Court of Australia database from 30 to 10 to avoid overloading it.
- Made minor micro-optimisations by replacing lambda functions with named functions.

### Fixed
- Skipped scraping web pages from the NSW Legislation database that contain the substring 'No fragments found.' due to a newly identified bug in the database (see, eg, https://legislation.nsw.gov.au/view/whole/html/inforce/2021-03-25/act-1944-031).
- Skipped scraping web pages from the Tasmanian Legislation database that contain the substring 'Content Not Found.' due to a newly identified bug in the database (see, eg, https://www.legislation.tas.gov.au/view/whole/html/inforce/current/act-2022-033).
- Fixed a bug wherein documents from the Federal Register of Legislation database stored as DOC files were parsed as DOCX files by searching for PDF versions instead or otherwise skipping them.

## [1.0.1] - 2024-02-17
### Fixed
- Refactored the scraper for the Federal Register of Legislation database in order to resolve breaking API changes brought about by the database's redesign, thereby fixing [#1](https://github.com/umarbutler/open-australian-legal-corpus-creator/issues/1).

## [1.0.0] - 2023-11-09
### Added
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

[3.0.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v2.0.0...v3.0.0
[2.0.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v0.1.2...v1.0.0
[0.1.2]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/umarbutler/open-australian-legal-corpus-creator/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/umarbutler/open-australian-legal-corpus-creator/releases/tag/v0.1.0