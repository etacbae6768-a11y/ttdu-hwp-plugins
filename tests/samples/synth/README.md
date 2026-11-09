# Synthetic HWP/HWPX samples (CC0-1.0)

40 generated files for testing HWP readers: 20 documents (`h-000` to `h-019`), each saved as
HWP 5 (`.hwp`) and HWPX (`.hwpx`), plus `truth.json` with the expected content.

- **Content is made up.** Each document has 1 to 10 body paragraphs and 0 to 3 tables (up to 4 x 4
  cells, some cells empty), built from a fixed list of 20 words and symbols: Korean and English words,
  an amount, a date, `「인용」`, `※`, `①`, `A&B` and `<태그>`. No real or personal data.
  In total: 123 paragraphs and 26 tables. There are no merged cells, nested tables, images, footnotes,
  headers or text boxes.
- **How they were made.** A seeded generator (seeds 9100 to 9119) wrote each document with the
  open-source engine `@rhwp/core` 0.8.6 (MIT): `createBlankDocument`, `insertText`, `splitParagraph`,
  `createTable`, `insertTextInCell`, then `exportHwp` and `exportHwpx`. The engine's built-in blank
  document supplies all other settings. For example, the `.hwp` files contain a preview-image temp
  path that comes from that template, and the `.hwpx` files name `rhwp` as the creator.
  The files were not made with Hancom software.
- **`truth.json`** is keyed by `synth/h-NNN` (one entry for both formats):
  `paragraphs` lists the non-empty body paragraph texts in order, and `tables` gives each body table
  as a row-major grid of cell texts (`""` for an empty cell).
- **Check.** The TTDU HWP reader returned exactly these paragraphs and table grids for all 40 files
  (2026-11-07).
- **License.** CC0 1.0 Universal (public domain dedication); see `LICENSE` in this folder.
  The rest of this repository is under the MIT License.

Hangul Word Processor (HWP) is a trademark of Hancom Inc. Not affiliated with Hancom Inc.
