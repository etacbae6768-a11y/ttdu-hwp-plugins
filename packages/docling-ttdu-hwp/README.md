# docling-ttdu-hwp

`.hwp` (HWP 5.x) and `.hwpx` input for [Docling](https://github.com/docling-project/docling). Builds a `DoclingDocument` (paragraphs; tables with merged-cell spans) so Docling's exporters and chunkers work on Korean word-processor documents.

```python
from docling_ttdu_hwp import convert_hwp, HwpAwareConverter
doc = convert_hwp("notice.hwp", backend="hub")
print(doc.export_to_markdown())

# .hwp/.hwpx through this package, everything else through Docling (pip install docling-ttdu-hwp[docling])
res = HwpAwareConverter(backend="local", local_key_file="local-api-key.txt").convert("report.hwpx")
```

Docling's plugin system covers OCR, layout and table engines, not input formats, so this is a separate converter rather than a Docling plugin.

## Where your document goes

- **Hub API (default, `TTDU_HWP_BACKEND=hub`): the document is sent over HTTPS to `toolsthatdontupload.com`**, read in memory for that request, and not stored. Without a key: 20 calls a day per IP; with a key (`TTDU_API_KEY`): 20 free file calls a day, then credits. Files up to 15 MB.
- **Local runner (`TTDU_HWP_BACKEND=local`)**: the offline runner on the same computer (`ttdu serve`, 127.0.0.1 only, key from `local-api-key.txt` via `TTDU_LOCAL_KEY_FILE`). The document does not leave the computer.

The first hub call warns once until `TTDU_HWP_BACKEND` is set. Full settings, error types and limits: see the repository README and https://toolsthatdontupload.com/docs/hwp/ .

## Notices

MIT license. This package contains no HWP parser; it calls the Tools That Don't Upload service (which reads documents with rhwp, MIT).
This product was developed with reference to the HWP document file (.hwp) specification published by Hancom Inc. Hangul Word Processor (HWP) is a trademark of Hancom Inc. Not affiliated with Hancom Inc.

한국어: 기본 설정(허브 API)에서는 문서가 toolsthatdontupload.com 서버로 전송됩니다(요청 동안 메모리 처리, 저장 안 함). 외부 전송이 안 되는 문서는 TTDU_HWP_BACKEND=local 로 같은 PC의 로컬 실행기를 쓰세요. 한글(HWP)은 ㈜한글과컴퓨터의 상표이며 이 프로젝트는 한컴과 관계가 없습니다.