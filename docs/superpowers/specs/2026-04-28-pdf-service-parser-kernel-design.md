# PDF Service Parser Kernel Design

## Summary

This spec defines a unified parsing kernel inside `pdf-service` to replace the current scattered regex-based question splitting logic. The new kernel must keep all existing API contracts and `models.py` field semantics unchanged while centralizing question boundary detection, material grouping, and visual assignment in one internal rule source.

The immediate implementation target is P0 only:

- add layered `parser_kernel` modules
- turn `question_splitter.py` into a compatibility shell
- route `TextStrategy` fallback through the unified kernel
- remove distributed `QUESTION_RE + next-match` splitting logic
- stop misclassifying directories, teaching text, and following material text as part of a question
- introduce two fixed validation fixtures with different parsing lanes
- support image-only scanned PDFs through a visual fallback that still feeds the same kernel data structures

P1 and P2 remain explicitly deferred until P0 is stable and verified.

## Constraints

- Scope is limited to `pdf-service` internals.
- Do not modify frontend, backend, API paths, or external task flow.
- Do not change the meaning of existing `models.py` fields.
- Do not add heavyweight PDF, OCR, or CV dependencies.
- Parsing must degrade with warnings and `needs_review`; a single bad page or question must not abort the whole book.
- All legacy entry points must ultimately call the unified kernel. No second splitting rule set may remain in `question_splitter.py`, `TextStrategy`, or any fallback path.
- The parser must distinguish between a normal question-book PDF and an answer-note / image-explanation PDF. The latter must not be forced through question splitting.
- The parser must also distinguish text-layer PDFs from scanned/image-only PDFs. Image-only PDFs must not silently return empty parse results when the page images are usable.

## Fixture Definitions

Two fixture PDFs are part of the accepted validation surface for this refactor:

1. `2026资料分析题库-test.pdf`

- role: `question_book`
- purpose: validate parser-kernel question boundaries, material grouping, and visual ownership
- expected lane: normal question parsing through the unified kernel

2. `test（7-12章下册完结）2026高照资料分析夸夸刷讲义复盘笔记（下册）.pdf`

- role: `answer_note` / `image_explanation`
- purpose: validate that heavily annotated review notes do not get treated as a normal question book
- expected lane: answer-book / image mode, preferring whole-page or cropped screenshots matched by question index, page number, or example anchor
- expected behavior: preserve image-oriented explanation content; do not force normal structured OCR question parsing

The second fixture contains handwriting, watermarks, screenshot rearrangement, and other layout noise. It is explicitly out of scope for `question_splitter` and the unified question-book splitting kernel.

Additional scanned fixtures are also in scope:

3. `题本篇.pdf`

- role: `scanned_question_book`
- purpose: validate image-only question-book routing and visual fallback extraction
- expected lane: visual extraction of suite title, material blocks, question anchors, options, and charts, then feed those candidates into the same parser-kernel grouping and adapter flow

4. `解析篇.pdf`

- role: `scanned_answer_book`
- purpose: validate that scanned answer/analysis PDFs are not treated like normal question books
- expected lane: answer-book / image-analysis mode keyed by `练习题xx套 + 题号`
- expected behavior: preserve cropped or whole-page screenshots when OCR is weak; do not fail empty because the PDF has no usable text layer

## Current Problems

The current parser has multiple incompatible boundary rules:

- `question_splitter.py` splits by `QUESTION_RE` and uses “next question anchor = current question end”.
- `TextStrategy._fallback_split()` duplicates the same assumption with its own local regex.
- Material prompts and body text are folded into neighboring questions because no material-group abstraction exists in the old path.
- Directory headings, chapter labels, and teaching text are frequently promoted into fake questions because anchor recognition is too shallow.
- Legacy visual binding behavior depends too much on position proximity and has no stable material-first ownership model.
- Annotated review-note PDFs can be mistakenly treated like question books even though their content is better handled as answer-book / image explanation input.
- Image-only scanned PDFs can collapse to empty or unusable results when the parser relies on the PyMuPDF text layer alone.

The result is parser drift between entry points and unstable behavior on data-analysis PDFs.

## Target Architecture

```txt
PDF
-> document_type_router
-> text-layer extraction or visual fallback extraction
-> parser_kernel.layout_engine
-> parser_kernel.semantic_segmenter
-> parser_kernel.question_group_builder
-> parser_kernel.visual_assignment
-> parser_kernel.adapter
-> existing models.py-compatible output
```

This architecture separates concerns:

- routing decides which extraction lane to use, but not how to split questions
- layout normalization turns source-specific input into one ordered element stream
- semantic segmentation decides what each element means
- group building creates material groups and question boundaries
- visual assignment decides whether visuals belong to a material group or a single question
- adapter maps kernel output into existing output structures

Question-book parsing and answer-note parsing remain separate lanes. This refactor only unifies the question-book lane; it must also preserve a clean routing boundary so answer-note/image-explanation PDFs are not misrouted into the kernel.

For scanned question books, the visual fallback is only a source lane. It must still emit the same internal data structures consumed by the parser kernel. No independent scanned-only splitting pipeline is allowed.

## PDF Type Model

The parser must classify incoming PDFs into one of these types:

1. `text_layer_book`
- usable text layer exists
- primary lane: PyMuPDF text + layout blocks

2. `scanned_question_book`
- text layer absent or too sparse for reliable parsing
- page images are clear enough for visual structure recovery
- primary lane: page screenshots + visual model extraction of suite title, material zones, question anchors, options, and charts/images
- output must still flow into the same parser-kernel grouping and adapter path

3. `scanned_answer_book`
- scanned analysis/answer booklet, not a normal question book
- primary lane: answer-book / image mode
- should build answer/analysis candidates by set and question number rather than forcing question-book splitting

Review-note / image-explanation PDFs remain a separate answer-note-oriented lane and are not equivalent to scanned question books.

## Internal Module Design

### `parser_kernel/types.py`

Defines internal-only structures used by the unified kernel.

Planned responsibilities:

- represent normalized elements from either page extraction or markdown extraction
- express semantic classifications without leaking `models.py` concerns
- capture group-level warnings and visual assignment scores

Representative internal concepts:

- `PageElement`
- `ElementKind`
- `SemanticRole`
- `QuestionAnchor`
- `QuestionGroup`
- `MaterialGroup`
- `AssignedVisual`
- `KernelWarning`

### `parser_kernel/layout_engine.py`

Normalizes source data into a single reading-order element stream.

Responsibilities:

- accept `PageContent[]` from `pdf_analyzer.extract_pages()`
- later accept markdown/layout-first payloads from `MarkdownQuestionStrategy`
- later accept visual-fallback extraction output for scanned question books
- convert text blocks and regions into uniformly typed `PageElement` records
- preserve page number, bbox, source text, and reading order

Non-responsibilities:

- deciding whether something is a real question
- deciding material ownership
- deciding final visual ownership
- deciding whether a PDF should be treated as a question book versus answer-note / image-explanation input

### `parser_kernel/routing.py`

Owns document-type routing.

Responsibilities:

- decide whether a PDF is:
  - `text_layer_book`
  - `scanned_question_book`
  - `scanned_answer_book`
  - or a non-question-book answer-note / image-explanation PDF
- prevent review notes and scanned answer books from entering normal question-book splitting
- detect image-only fallback conditions for question books

Routing may use:

- file naming hints
- extracted text density
- page-level text availability
- answer-book/review-note structural markers

Routing must not contain question-boundary rules.

### `parser_kernel/semantic_segmenter.py`

Owns the only text-driven splitting rules in the system.

Responsibilities:

- identify candidate question anchors
- reject false anchors from directory-like headings, chapter labels, and teaching text
- classify material prompts and material body
- classify options
- classify question stem continuation
- mark suspicious spans with warnings instead of aborting

This module is the only allowed home for anchor-recognition regexes and heuristics.

### `parser_kernel/question_group_builder.py`

Owns question boundaries and material grouping.

Responsibilities:

- build `MaterialGroup` objects from segmented elements
- assign questions to a material group when the evidence is strong enough
- keep following material text out of the previous question
- keep question-local stem boundaries from absorbing the next section
- downgrade uncertain cases into warnings and `needs_review`

Boundary policy:

- question end is not defined purely by the next anchor
- group building combines anchor transitions, semantic role changes, option structure, and material prompts

### `parser_kernel/visual_assignment.py`

Owns visual ownership.

Responsibilities:

- evaluate whether each visual belongs to a material group or a single question
- prefer material ownership when a visual is shared by a material-based question set
- compute `assignment_confidence`
- emit visual warnings for unassigned or low-confidence cases

Visual assignment must not regress to a simple nearest-y heuristic.

### `parser_kernel/adapter.py`

Owns mapping from internal kernel output into existing external shapes.

Responsibilities:

- produce `RawQuestion[]` for compatibility consumers
- produce strategy payloads shaped like `{"questions": ..., "materials": ...}`
- preserve current field semantics for:
  - `material_id`
  - `page_num`
  - `page_range`
  - `source_bbox`
  - `source_anchor_text`
  - `source_confidence`
  - `image_refs`
  - `parse_confidence`
  - `parse_warnings`
  - `needs_review`
  - `assignment_confidence` inside image payloads

Adapter logic must not redefine parsing rules.

### Visual Fallback Extraction

Scanned question books require a source lane that does not depend on the PyMuPDF text layer.

Responsibilities of the visual extraction lane:

- render whole pages or stable crops
- invoke the existing visual model stack already available in `pdf-service`
- recover:
  - suite title
  - material blocks
  - question anchors
  - option blocks
  - charts/images
- emit normalized element candidates into the same parser-kernel structures

Constraints:

- do not add heavyweight new dependencies
- do not create a second scanned-only splitting pipeline
- if OCR is weak, preserve page or region screenshots as evidence rather than failing empty

## Lane Routing Requirement

The refactor must preserve a hard distinction between:

- `text_layer_book` PDFs: parsed through the unified `parser_kernel`
- `scanned_question_book` PDFs: visually extracted, then parsed through the unified `parser_kernel`
- `answer_note` / `image_explanation` / `scanned_answer_book` PDFs: handled by answer-book or image-based explanation flow

The review-note fixture must be routed away from `question_splitter` and any normal next-question boundary logic. It should prefer whole-page or region screenshots linked by:

- question index
- source page number
- example anchor such as `例1`, `例2`

For this class of document, preserving image-heavy explanation context is more important than forcing full structural OCR.

For scanned answer books, preserving recoverable answer/analysis candidates and screenshot evidence is more important than forcing structured question parsing.

## Existing File Changes

### `question_splitter.py`

Becomes a compatibility shell only.

It will:

- keep its current import-facing role
- call the unified kernel
- return `RawQuestion[]`

It will no longer:

- define the authoritative splitting regex
- use “next match = end of current question”
- maintain local material attachment heuristics

### `strategies/text_strategy.py`

AI-first behavior stays in place, but fallback must use the unified kernel.

It will:

- retain answer-page detection and answer merge
- delegate fallback question parsing to `parser_kernel`

It will no longer:

- keep a private `QUESTION_RE`
- keep `_fallback_split()` as an independent splitting implementation
- keep `_fallback_parse_question()` as a second boundary rule source

### `strategies/markdown_question_strategy.py`

Deferred to P2, but the design requirement is fixed now:

- markdown/layout-first parsing must eventually reuse the same parser kernel
- markdown strategy may keep source-specific extraction code, but not source-specific question-boundary governance

### `block_segmenter.py`

Deferred to P2:

- progressively thin out current mixed responsibilities
- retain only utilities that still make sense after the new kernel is introduced

## Legacy Logic To Remove or Deprecate

The following logic must be deleted or rendered unreachable:

1. `pdf-service/question_splitter.py` local `QUESTION_RE`
2. `pdf-service/question_splitter.py` “question end = next question start”
3. `pdf-service/strategies/text_strategy.py` local `QUESTION_RE`
4. `pdf-service/strategies/text_strategy.py::_fallback_split`
5. `pdf-service/strategies/text_strategy.py::_fallback_parse_question`

Anchor-matching regexes may remain only inside `parser_kernel.semantic_segmenter`.

## Warning and Review Policy

The kernel must prefer partial output over hard failure.

### Warnings

Expected warning families include:

- `directory_like_heading`
- `teaching_text_mixed`
- `multiple_question_anchors`
- `options_incomplete`
- `material_range_uncertain`
- `material_or_visual_missing`
- `visual_unassigned`
- `visual_assignment_low_confidence`
- `cross_page_boundary_uncertain`

### `needs_review`

Set `needs_review = true` when any of the following holds:

- structural warning exists
- options are incomplete for a single-choice question
- question boundary is uncertain
- material ownership is uncertain
- visual assignment is low confidence
- raw span contains multiple candidate anchors
- cross-page grouping is unstable

### `assignment_confidence`

Owned only by the visual-assignment layer.

Suggested interpretation:

- `>= 0.80`: high confidence
- `0.65 - 0.79`: acceptable but may still warn
- `< 0.65`: low confidence and `needs_review`

## Failure Tolerance

- Page-level exceptions must not stop the book. Record warnings and continue.
- A material-group failure must degrade to standalone questions when needed.
- Visual assignment failure must keep output, add warnings, and mark review.
- Single-question parse anomalies must not abort the page or batch.

## P0 Scope

P0 includes:

- create `parser_kernel` layered modules
- wire `question_splitter.py` to the kernel
- wire `TextStrategy` fallback to the kernel
- remove duplicate linear next-match splitting implementations
- prevent directory/teaching/next-material text from being mis-cut into questions
- add minimum regression tests
- register and use the question-book fixture in parser-kernel validation
- add a routing safeguard test so the review-note fixture shape is not treated as a normal question-book input
- define document-type routing interfaces that support scanned question books and scanned answer books without adding a second splitting rule source

P0 explicitly excludes:

- markdown strategy full migration
- `block_segmenter.py` thinning
- richer debug bundle expansion beyond what is needed for P0

If full scanned visual extraction is too broad for the first pass, P0 still must establish the routing and normalized input interfaces immediately so the scanned fallback can enter the same kernel structures without redesign.

## Minimum Verification Set

P0 is considered acceptable only if the following tests pass:

1. standard single question parses into one question with complete options
2. material prompt plus three linked questions produces one material group and three linked questions
3. following material text does not get absorbed into the previous question
4. directory headings and teaching text do not become normal questions
5. fallback path in `TextStrategy` uses the unified kernel instead of local next-match splitting
6. review-note / image-explanation fixture shape is not sent through `question_splitter`
7. scanned question books are recognized as image-only question books rather than empty text-layer failures
8. scanned answer books are not sent through normal question-book splitting

## Implementation Order

1. Build internal kernel types and layout normalization for `PageContent[]`
2. Implement semantic segmentation and group building for P0 coverage
3. Replace `question_splitter.py` internals with kernel delegation
4. Replace `TextStrategy` fallback internals with kernel delegation
5. Remove or neutralize legacy distributed splitters
6. Add minimum regression tests
7. Verify that output shape remains compatible with existing `models.py`

## Risks

- Existing tests are sparse, so behavior regressions must be locked with new parser-kernel tests first.
- Some current markdown-path utilities overlap conceptually with the new kernel; delaying P2 avoids uncontrolled scope growth.
- Because this workspace is not a git repository root, spec and plan artifacts can be written but cannot be committed from here.
