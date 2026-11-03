# Maintaining the documentation

The living documentation is written in English. The pages under "Project
history" and "Benchmark research" are dated records and keep their original
language.

Source of truth by section:

| Section | Source | Update |
|---|---|---|
| Workflow (`workflow.md`) | Written by hand | On every change of pipeline behaviour |
| API reference (`reference/api.md`) | Docstrings in `src/` and `dashboard/` | Automatic — `mkdocstrings` regenerates it at build time |
| ADR (`adr/`) | Written by hand, one file per decision | On every significant architecture decision |
| Plans (`plans/`) | Written by hand | When an implementation plan is created or closed |

## Before committing a documentation change

```bash
make docs-build   # strict validation (links, navigation, mkdocstrings)
make docs-serve   # local preview with live reload
```

`make docs-build` (strict mode) fails when:

- an internal link points to a missing page or to a page outside `nav` (see `mkdocs.yml`);
- a module referenced by a `::: module.path` directive cannot be imported;
- mkdocs reports a warning (warnings are errors in strict mode).

## Adding a module to the API reference

1. Add the module to `docs/reference/api.md` with a `::: module.path` directive.
2. The module must import without module-level side effects (no file reads and
   no network calls at import time).
3. Run `make docs-build` to validate before committing.
