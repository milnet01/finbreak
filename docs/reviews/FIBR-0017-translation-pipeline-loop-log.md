# FIBR-0017 translation pipeline — loop log

The record for [`../specs/FIBR-0017-translation-pipeline.md`](../specs/FIBR-0017-translation-pipeline.md).

## Cold-eyes loop log

| Loop | Date | Q1 | Q2 | Q3 | Q4 | Outcome | Commit |
|------|------|----|----|----|----|---------|--------|
| amend | 2026-11-15 | — | — | — | — | Not a review: fold-back from the build. § 4.4 names `language_name`, because `nativeLanguageName()` reads "American English" for `en`. | this commit |
| amend | 2026-11-15 | — | — | — | — | Not a review: close-findings on the review-code lane of 2026-11-15. § 4.2 resolves over `uiLanguages()` and finds a regional qtbase catalog; § 4.4 names give `pt_BR` its territory; § 6 logs a catalog that will not load; INV-4, INV-5 and INV-8 name their new tests. | this commit |
| amend | 2026-11-18 | — | — | — | — | Not a review: the five AI-drafted catalogs shipped (user decision 2026-11-18). Layman, § 3's scope bullet and § 9 now say so; § 3 names `MACHINE_TRANSLATED`. No reviewer dispatched. | this commit |
| amend | 2026-11-18 | — | — | — | — | Not a review: close-findings on the /code-review of 033c46b..HEAD. § 3's bullet now names `REVIEWED`, which replaces `MACHINE_TRANSLATED`, so an unlisted catalog is labelled; § 4.4 names bare `es` "español". No reviewer dispatched. | this commit |
| amend | 2026-11-21 | — | — | — | — | Not a review: FIBR-0485. § 4.2 and INV-1 add a same-language, same-script step before English, for entries that name their script, so `zh_SG` gets `zh_CN` and `zh_TW` still gets English. INV-1's test gains the three cases. No reviewer dispatched. | this commit |
