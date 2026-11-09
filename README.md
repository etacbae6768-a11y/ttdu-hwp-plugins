# HWP/HWPX plugins for MarkItDown and Docling

Read Korean word-processor documents (`.hwp` HWP 5.x and `.hwpx`) in AI document pipelines.

| Package | What it adds |
|---|---|
| [`markitdown-ttdu-hwp`](packages/markitdown-ttdu-hwp) | A [MarkItDown](https://github.com/microsoft/markitdown) plugin: `.hwp`/`.hwpx` → Markdown (paragraphs, tables) |
| [`docling-ttdu-hwp`](packages/docling-ttdu-hwp) | [Docling](https://github.com/docling-project/docling) input: `.hwp`/`.hwpx` → `DoclingDocument` (tables keep merged-cell spans) |
| [`ttdu-hwp`](packages/ttdu-hwp) | The shared client and a small CLI (`ttdu-hwp file.hwp --to markdown|text|json|docx`). Standard library only |

These packages **do not contain an HWP parser**. They are thin clients that call the
conversion service of [Tools That Don't Upload](https://toolsthatdontupload.com/docs/hwp/) in one of two ways.

## Where your document goes

| Backend | Setting | What happens to the file |
|---|---|---|
| **Hub API** (default) | `TTDU_HWP_BACKEND=hub` | **The document is sent over HTTPS to `toolsthatdontupload.com`** (a Cloudflare Worker), read in memory for that one request, and the document and result are not stored. The usual minimal request record applies ([privacy policy](https://toolsthatdontupload.com/privacy/)). |
| **Local runner** | `TTDU_HWP_BACKEND=local` | The document goes to the offline runner on the same computer (`ttdu serve`, listening on `127.0.0.1` only). It does not leave the computer. |

Until you set `TTDU_HWP_BACKEND` explicitly, the first hub call prints a one-time warning saying
where the file is being sent. Do not use the hub backend for documents you are not allowed to send
to a third-party service; use the local runner instead.

## Install

```bash
pip install markitdown-ttdu-hwp      # MarkItDown plugin (pulls in ttdu-hwp)
pip install docling-ttdu-hwp         # Docling input (pulls in docling-core and ttdu-hwp)
```

## Use

MarkItDown (plugins are off by default in MarkItDown, so turn them on):

```bash
export TTDU_HWP_BACKEND=hub          # or: local
export TTDU_API_KEY=ttdu_...         # optional
markitdown --use-plugins notice.hwp > notice.md
```

```python
from markitdown import MarkItDown
md = MarkItDown(enable_plugins=True, ttdu_hwp_backend="hub")   # options can also be passed here
print(md.convert("notice.hwpx").markdown)
```

Docling:

```python
from docling_ttdu_hwp import convert_hwp, HwpAwareConverter
doc = convert_hwp("notice.hwp", backend="local", local_key_file="C:/ttdu-office/local-api-key.txt")
print(doc.export_to_markdown())

# Mixed folders: .hwp/.hwpx through this package, everything else through Docling (needs `docling`)
result = HwpAwareConverter().convert("report.hwpx")
```

## Settings

| Option (Python) | MarkItDown keyword | Environment variable | Default |
|---|---|---|---|
| `backend` | `ttdu_hwp_backend` | `TTDU_HWP_BACKEND` | `hub` |
| `api_key` | `ttdu_api_key` | `TTDU_API_KEY` | none |
| `hub_url` | `ttdu_hub_url` | `TTDU_HUB_URL` | `https://toolsthatdontupload.com` |
| `local_url` | `ttdu_local_url` | `TTDU_LOCAL_URL` | `http://127.0.0.1:8790` |
| `local_key` | `ttdu_local_key` | `TTDU_LOCAL_KEY` | read from `local_key_file` |
| `local_key_file` | `ttdu_local_key_file` | `TTDU_LOCAL_KEY_FILE` | none (path to `local-api-key.txt`) |
| `timeout` | `ttdu_timeout` | `TTDU_HWP_TIMEOUT` | 120 s |

`local_url` must point at `127.0.0.1`, `localhost`, `::1` or `host.docker.internal`; the client refuses
other hosts so a misconfiguration cannot send files somewhere else.

## Limits and cost (hub)

Same rules as the [HWP API](https://toolsthatdontupload.com/docs/hwp/): one conversion is one file call.
Without a key, 20 calls a day per IP address. With a key, 20 free file calls a day, then credits.
Files up to 15 MB (checked before sending, so an oversized file does not use a call).
The local runner accepts files up to 200 MB and has no call quota.

## Errors

All errors derive from `ttdu_hwp.HwpError` and carry `.code`, `.status` and `.details`.

| Exception | When | `code` |
|---|---|---|
| `EncryptedDocumentError` | Password- or distribution-protected document | `unsupported` |
| `InvalidDocumentError` | Damaged file, or not an HWP 5.x / HWPX document | `invalid_input` |
| `LimitExceededError` | Too large, or a damaged file asked for too much memory | `resource_limit` |
| `QuotaExceededError` | Daily quota / rate limit / credits used up (`.retry_after` in seconds when known) | from the service |
| `AuthenticationError` | Wrong API key, or wrong local runner key | from the service |
| `ServiceUnavailableError` | Network error, timeout, local runner not running, server error | `unavailable` |
| `ConfigurationError` | Unknown backend, local URL not on this computer, missing local key | `configuration` |

In MarkItDown, a converter error is reported inside `FileConversionException` with the message above.

## What is kept

Body paragraphs in order, line breaks, and tables (merged cells: Markdown leaves the covered
positions empty; Docling keeps row/column spans). Tables inside table cells follow their parent table.
Not kept: layout, fonts, colors, images and drawings. Headers, footers, footnotes and text boxes may be missing.

## Local runner

The local runner is part of the Tools That Don't Upload office package (a Windows folder with its own
Node.js runtime, no installation). Start `ttdu serve` (or `로컬API.cmd`); it prints its address and the path
of `local-api-key.txt`. Then set `TTDU_HWP_BACKEND=local` and `TTDU_LOCAL_KEY_FILE` to that path.
The runner blocks outgoing network connections while it converts.

## Tests

`tests/` has unit tests (no network) and `scripts/compare.py`, which converts sample documents through both
backends and checks that the plugins give the same result as the hub API.

## License and notices

MIT, see [LICENSE](LICENSE). The conversion service itself is not part of this repository.

The service reads documents with [rhwp](https://github.com/edwardkim/rhwp) (MIT).
This product was developed with reference to the HWP document file (.hwp) specification published by Hancom Inc.
Hangul Word Processor (HWP) and Hancom are trademarks of Hancom Inc. This project is not affiliated with,
endorsed by or sponsored by Hancom Inc., Microsoft (MarkItDown) or the Docling project.

---

## 한국어 요약

- `.hwp`(HWP 5.x)·`.hwpx` 문서를 MarkItDown·Docling 에서 읽게 해 주는 플러그인입니다. 변환기 자체는 들어 있지 않고 우리 서비스를 부릅니다.
- **기본(허브 API)으로 쓰면 문서가 `toolsthatdontupload.com` 서버로 전송됩니다.** 그 요청 동안 메모리에서만 처리하고 문서·결과는 저장하지 않습니다.
- 외부로 보내면 안 되는 문서는 `TTDU_HWP_BACKEND=local` 로 같은 PC 의 로컬 실행기(`ttdu serve`, 127.0.0.1 전용)를 쓰세요. 문서가 PC 밖으로 나가지 않습니다.
- 한도: 키 없이 IP당 하루 20회, 키가 있으면 하루 무료 20회 뒤 크레딧. 파일 15 MB(로컬 200 MB).
- 이 제품은 한글과컴퓨터의 한글 문서 파일(.hwp) 공개 문서를 참고하여 개발하였습니다. 한글(HWP)·한컴은 ㈜한글과컴퓨터의 상표이며, 이 프로젝트는 한글과컴퓨터와 관계가 없습니다.
