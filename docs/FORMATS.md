# OpenTDF format naming (specs vs software)

This fork uses **official OpenTDF / Virtru terminology** for format profiles
and software stacks. See also [opentdf.io/spec](https://opentdf.io/spec) and
[Virtru Trusted Data Format](https://www.virtru.com/data-security-platform/trusted-data-format).

## Format naming (specifications)

| Official name | Test slug | What it is |
|---------------|-----------|------------|
| **Base TDF** / **Standard TDF** | `tdf` (aliases: `base-tdf`, legacy `ztdf`) | Foundational open format: JSON manifest inside a ZIP archive plus encrypted payload. This is what OpenTDF SDKs implement by default. |
| **ZTDF** (Zero Trust Data Format) | `ztdf` *(reserved; not Stage-1)* | Open specialized profile (NATO / Five Eyes heritage) that builds on OpenTDF with strict cryptographic assertions and metadata bindings (STANAG-oriented). **Not** a synonym for “ZIP TDF”. |
| **NanoTDF** | `nanotdf` *(not Stage-1)* | Binary compact variant for constrained / streaming environments. |
| **IC-TDF** | — | Older XML-based Intelligence Community variant (out of scope here). |

### Base TDF variants in this suite

| Slug | Meaning |
|------|---------|
| `tdf` | Base TDF, default RSA wrap |
| `tdf-ecwrap` | Base TDF with EC key wrapping |

Legacy OpenTDF tooling (including official `cli.sh` 4th-argument wire format)
often used the string `ztdf` for Base TDF ZIP containers. The harness still
**accepts** that alias and still **emits** `ztdf` on the wire to go/java/js
shims. Canonical names in pytest, docs, and CI are `tdf` / `tdf-ecwrap`.

```bash
# Preferred
pytest --containers tdf tdf-ecwrap

# Still works (legacy alias → Base TDF)
pytest --containers ztdf ztdf-ecwrap
```

## Implementation naming (software)

| Name | Role |
|------|------|
| **OpenTDF** | Open-source platform, KAS, policy, and SDKs ([github.com/opentdf](https://github.com/opentdf)). Enforces Base TDF. |
| **Virtru Data Security Platform (DSP)** | Commercial product that builds on OpenTDF and adds enterprise / government capabilities (including environments that consume ZTDF, STANAG tagging, HSMs, etc.). |

Do **not** use “Virtru TDF” or “OpenTDF format” as if they were interchangeable format names. Prefer **Base TDF** for the open ZIP+JSON format and **OpenTDF** for the software stack under test.

## Stage-1 community conformance

| In scope | Out of scope |
|----------|----------------|
| Base TDF (`tdf`) community ↔ `go@main` | NATO ZTDF profile |
| | NanoTDF |
| | Full ABAC / PQC / multi-KAS matrix |

## References

- OpenTDF specification: https://opentdf.io/spec  
- OpenTDF architecture: https://opentdf.io/architecture  
- Virtru TDF overview: https://www.virtru.com/data-security-platform/trusted-data-format  
