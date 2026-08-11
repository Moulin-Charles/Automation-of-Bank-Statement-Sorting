# Bank statement extractor

[![CI](https://github.com/USER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/USER/REPO/actions/workflows/ci.yml)

**English (en)** · [Français (fr)](README.fr.md)

Turns a bank statement (PDF) into a spreadsheet — on statements that
contain no text whatsoever.

## The problem

Pulling transactions out of a bank statement should be a solved problem. Every
tool returns nothing:

```console
$ pdftotext statement.pdf -

>>> pdfplumber.open("statement.pdf").pages[0].extract_text()
''
```

Nine pages, eighty-seven transactions, and not one character of text. The PDF
has no text layer at all: the generator converts the font to outlines before
writing the file, so every character is stored as a set of filled vector
paths. There is no `A` anywhere in the document — only the *shape* of an A.

Worse, the outlines are re-quantised at each occurrence. Two `A`s on the same
page are never geometrically identical, so the characters cannot be recovered
by looking up repeated paths either.

## Why the usual answers don't apply

**Text extraction** has nothing to extract. `pdftotext`, `pdfplumber` and
`pypdfium2` all return an empty string, because they are all asking the file
for content it does not carry.

**OCR** is the standard fallback: rasterise the page, run Tesseract. It would
mostly work. But it throws away information that is right there — the exact
geometry of every glyph — and replaces it with a statistical guess about
pixels. On a bank statement the failure mode of a guess is a silently wrong
amount, which is precisely the thing you cannot tolerate.

The outlines are exact. The layout is monospace. That is enough to decode the
page without guessing.

## The approach

1. **Lines.** Every filled path on the page is collected and grouped by its
   baseline. Descenders and parentheses drop below the line and would create
   phantom baselines, so candidates closer than 5 pt are folded onto the
   best-supported one.

2. **The grid.** The statement is set in a monospace font, so glyph positions
   are `origin + n × pitch`. Both are recovered by maximising the circular
   mean of `x mod p` over the plausible pitch range — the true pitch is the one
   at which every glyph's x-coordinate lands in phase. It comes out at
   ≈ 5.97 pt.

3. **Fingerprints.** Each grid cell is rasterised at 8× and its paths are
   XOR-composited, which turns the even-odd fill rule into working counters —
   the holes in `o`, `e` and `8` come out for free. The cell is then box-
   downsampled to 12 × 18 and flattened into a 217-dimensional vector: 216
   normalised coverage values plus one ink-quantity term.

4. **Classification.** Nearest neighbour against 162 learned fingerprints. A
   cell further than a fixed distance from every model glyph is reported as
   `?` with a warning, rather than being guessed at.

5. **Parsing.** The reconstructed text is a fixed-column ledger, read with
   regular expressions: balance lines, transaction headers, and the wrapped
   description lines beneath each one.

## The statement checks itself

The reason this is trustworthy rather than merely clever: the extractor
recomputes `opening balance + Σ amounts` and compares it against the closing
balance printed on the last page.

```console
$ python extract_releve.py statement.pdf
87 operations, solde initial 1,581.47 EUR, solde final 3,863.03 EUR
Controle : OK
Ecrit -> statement.xlsx
```

`Controle : OK` means every amount and every sign was read correctly — a
single misread digit breaks the arithmetic and says so. This is what makes a
home-made character recogniser acceptable for financial data: it is not
trusted, it is verified, on every run.

In its first month of use the reconciliation surfaced three data-entry
mistakes in the budget spreadsheet it feeds.

## Install

```console
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11+. Four dependencies: `pdfplumber`, `numpy`, `Pillow`, `openpyxl`.

## Usage

Extract a statement to a spreadsheet:

```console
python extract_releve.py statement.pdf [-o output.xlsx]
```

The workbook has one row per transaction — date, value date, number, type,
counterparty, counterparty IBAN, communication, reference, card, direction,
debit, credit, amount, running balance, raw description, page — framed by the
opening and closing balance rows.

`preremplir_budget.py` then carries those transactions into a monthly budget
workbook, giving each one a short label and a category from a set of JSON
rules. It writes nothing by default; `--ecrire` applies, after taking a dated
backup.

```console
python preremplir_budget.py statement.xlsx            # dry run, prints a report
python preremplir_budget.py statement.xlsx --ecrire   # apply
```

It skips internal transfers and salary, merges same-day instalments of one
purchase, and detects what is already in the workbook (same amount within
5 days) so a re-run cannot duplicate entries. Unmatched lines land in a
`À CLASSER` category rather than being force-fitted.

## Tests

```console
pip install -r requirements-dev.txt
pytest -v
```

**No real statement exists in this repository, and none ever has.** The tests
run against a fully synthetic one, built in two parts:

- `tools/extraire_glyphes.py` extracts a *glyph library* from a real statement
  kept outside the repository — for each character, the vector outlines of one
  occurrence, relative to its cell. This is font geometry and nothing else: the
  outline of an `A` is an `A` whatever statement it came from.
- `tools/faire_releve_exemple.py` draws those outlines into a new PDF from
  invented content — `tests/data/releve_exemple.json`, with made-up names,
  merchants and amounts, and the IBANs banks publish as examples.

The result is a PDF with the same property as the real thing — no text layer,
every character in outlines — whose expected content is known exactly. The
tests assert that the extractor recovers it: the balance reconciles, no
transaction is lost, labels come back verbatim, and every transaction type is
classified correctly.

A CI job additionally refuses any commit carrying a PDF or spreadsheet other
than the sample.

## Known limitations

- **`O` and `0` are the same shape.** In this bold face the letter and the
  digit are drawn identically, and no amount of fingerprinting separates them:
  the classifier decides by a hair and is sometimes wrong. It does not matter
  where it counts — numeric fields force a digit reading before parsing — but a
  label may come back as `S0LDE`.
- **One bank, one layout.** The column positions, the balance lines and the
  transaction grammar are specific to the issuing bank. Another bank means
  another parser.
- **The model covers what it has seen.** A character absent from the 162
  fingerprints is reported as `?` with a warning; the fix is to retrain the
  model, not to patch the parsing.

## Layout

```
extract_releve.py       PDF -> spreadsheet: decoding, parsing, Excel export
preremplir_budget.py    spreadsheet -> monthly budget workbook
regles_categories.json  example classification rules (yours go in a .local. file)
glyph_model.npz         162 glyph fingerprints
tools/                  building the synthetic sample statement
tests/                  the suite, and the sample it runs on
```

## Development notes

The extraction algorithm — glyph fingerprinting, grid-fitting, balance
reconciliation — is original work, developed and validated on real statements
before this repository existed. The repository around it — test suite, CI
pipeline, packaging, documentation, and the anonymised sample data — was
structured with AI-assisted tooling, to make the codebase easier to install,
verify, and read.

## Licence

MIT — see [LICENSE](LICENSE).
