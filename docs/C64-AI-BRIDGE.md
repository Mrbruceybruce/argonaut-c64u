# C64-side AI bridge: first interface

Argonaut's Test Lab determines pass or fail in ordinary code. Its AI diagnosis
reads sanitized failure evidence afterward. The C64-side assistant is a
different use of a model: it accepts a short user question and returns short
screen text. It does not receive a Test Lab report, credentials, or a C64U
control object.

The first bridge is a loopback-only HTTP prototype in `c64_ai_chat.py` and
`c64_ai_service.py`. It accepts `POST /v1/chat` with `Content-Type: text/plain`,
an authorization bearer token, and one printable ASCII question of at most
240 bytes. The answer is at most 512 printable ASCII bytes, with a fixed
`Content-Length` and `Cache-Control: no-store`. The C64 client will translate
the text to PETSCII and wrap it to 40 columns. The model is local Ollama only;
the current bridge has no cloud selection or device actions.

The prototype deliberately binds to `127.0.0.1`, so a C64U cannot reach it
yet. Before enabling a listener on the home LAN, add private token pairing,
identity or address restriction to the intended C64U, and a simple way to
start and stop the bridge. The listener should never expose Ollama itself.

For the C64 program, use the Ultimate Command Interface (UCI) Network target
`$03` to open a TCP socket, send a small HTTP request, and read the bounded
reply. Probe `$03 $01` first, so a missing or disabled Command Interface is
shown as a clear error. The official [Network Target documentation](https://1541u-documentation.readthedocs.io/en/latest/uci/network_target.html)
defines `OPEN_TCP`, `WRITE_SOCKET`, `READ_SOCKET`, and `CLOSE_SOCKET` for
Ultimate products including the Commodore 64 Ultimate. The UCI command queue
is 896 bytes, so request construction must stay within that bound or split
socket writes; the [UCI register documentation](https://1541u-documentation.readthedocs.io/en/latest/uci/core_uci_architecture.html)
also requires checking completion and status rather than assuming success.

The newer UCI HTTP target `$06` offers an easier path on firmware that
supports it, but the [official HTTP Target documentation](https://1541u-documentation.readthedocs.io/en/latest/uci/http_target.html)
describes it as a 3.15-era feature. Bruce's two C64Us currently report
`1.1.0` and `1.1.0s2`; the C64 program must probe target `$06 $01` before
selecting that path. No firmware change is required for this first step.

The next implementation step is a C64U-side capability probe and minimal
PETSCII client, tested first in a simulation or emulator. LAN pairing and a
private listener can follow once the program's transport is working.
