# markitdown-ttdu-hwp

A [MarkItDown](https://github.com/microsoft/markitdown) plugin that converts `.hwp` (HWP 5.x) and `.hwpx` Korean word-processor documents to Markdown: paragraphs in order and tables as Markdown tables.

```bash
pip install markitdown-ttdu-hwp
export TTDU_HWP_BACKEND=hub   # or local
markitdown --use-plugins notice.hwp
```

```python
from markitdown import MarkItDown
md = MarkItDown(enable_plugins=True, ttdu_hwp_backend="hub")
print(md.convert("notice.hwpx").markdown)
```

Keyword options for `MarkItDown(...)`: `ttdu_hwp_backend`, `ttdu_api_key`, `ttdu_hub_url`, `ttdu_local_url`, `ttdu_local_key`, `ttdu_local_key_file`, `ttdu_timeout` (environment variables `TTDU_*` otherwise).

## Where your document goes

- **Hub API (default, `TTDU_HWP_BACKEND=hub`): the document is sent over HTTPS to `toolsthatdontupload.com`**, read in memory for that request, and not stored. Without a key: 20 calls a day per IP; with a key (`TTDU_API_KEY`): 20 free file calls a day, then credits. Files up to 15 MB.
- **Local runner (`TTDU_HWP_BACKEND=local`)**: the offline runner on the same computer (`ttdu serve`, 127.0.0.1 only, key from `local-api-key.txt` via `TTDU_LOCAL_KEY_FILE`). The document does not leave the computer.

The first hub call warns once until `TTDU_HWP_BACKEND` is set. Full settings, error types and limits: see the repository README and https://toolsthatdontupload.com/docs/hwp/ .

## Notices

MIT license. This package contains no HWP parser; it calls the Tools That Don't Upload service (which reads documents with rhwp, MIT).
This product was developed with reference to the HWP document file (.hwp) specification published by Hancom Inc. Hangul Word Processor (HWP) is a trademark of Hancom Inc. Not affiliated with Hancom Inc.

한국어: 기본 설정(허브 API)에서는 문서가 toolsthatdontupload.com 서버로 전송됩니다(요청 동안 메모리 처리, 저장 안 함). 외부 전송이 안 되는 문서는 TTDU_HWP_BACKEND=local 로 같은 PC의 로컬 실행기를 쓰세요. 한글(HWP)은 ㈜한글과컴퓨터의 상표이며 이 프로젝트는 한컴과 관계가 없습니다.