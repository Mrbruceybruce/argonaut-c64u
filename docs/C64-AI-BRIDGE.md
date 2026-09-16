# C64-side AI bridge: first interface

Argonaut's Test Lab determines pass or fail in ordinary code. Its AI diagnosis
reads sanitized failure evidence afterward. The C64-side assistant is a
different use of a model: it accepts a short user question and returns short
screen text. It does not receive a Test Lab report, credentials, or a C64U
control object.

The first bridge starts as loopback-only in `c64_ai_chat.py` and can use a
paired LAN listener from `c64_ai_service.py`. It accepts `POST /v1/chat` with `Content-Type: text/plain`,
an authorization bearer token, and one printable ASCII question of at most
240 bytes. The answer is at most 512 printable ASCII bytes, with a fixed
`Content-Length` and `Cache-Control: no-store`. The C64 client will translate
the text to PETSCII and wrap it to 40 columns. The model is local Ollama only;
the current bridge has no cloud selection or device actions.

The LAN listener binds one explicit address, requires a private token, and
accepts only the known addresses of the selected C64U. Supporting both its
Ethernet and Wi-Fi addresses does not pair another device. A simple way to
start and stop the bridge is still required. The listener never exposes Ollama
itself.

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

The next implementation step is a minimal PETSCII client and a temporary,
paired LAN listener. The listener must accept requests only from the selected
C64U and must still require its private bearer token.

The first capability probe is now in `c64/uci-network-probe.bas`; its tokenized
`c64/uci-network-probe.prg` is a small C64 BASIC program. It checks the UCI
identification register, sends only the Network target's `IDENTIFY` command,
checks the status bytes, and reports either `UCI NETWORK READY`, a missing
Command Interface, or a network target error. It does not change settings or
open a network connection. Rebuild with `petcat -w2 -f -o
c64/uci-network-probe.prg c64/uci-network-probe.bas`. It has been compiled and
round-tripped through VICE's `petcat`.

On 2026-09-15 the probe was run on Bruce's identity-bound Ethernet C64U after
enabling its runtime `Command Interface` setting. It returned `UCI NETWORK
READY` and `ULTIMATE-II NETWORK INTERFACE V1.0`. The setting was not saved to
flash, and the second C64U was not changed. This verifies target `$03` on the
current C64U 1.1.0 firmware without relying on the later HTTP target.

`c64/uci-network-info.prg` reads the UCI interface count and addresses without
changing them. The same C64U reported Ethernet `192.168.68.69` and Wi-Fi
`192.168.68.66`, both with a `/22` mask and gateway `192.168.68.1`. Its UCI
socket could connect to an existing service on the Argonaut computer, proving
the TCP route works, while the new bridge port remained blocked when the
firewall allowed only `.69`. The paired listener therefore supports both known
addresses; the firewall should do the same until firmware offers explicit
per-socket interface selection or Wi-Fi is disabled by a supported setting.
