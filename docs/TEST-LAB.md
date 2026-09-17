# Argonaut Test Lab foundation

Run the offline and simulated protocol checks with `python3 -m c64u_browser.test_lab`.
The command prints a versioned JSON report and exits nonzero when any check fails.
It does not connect to a C64U or modify device settings.

To exercise the failure and AI diagnosis path without waiting for real hardware
to fail, run `python3 -m c64u_browser.test_lab --suite diagnosis_probe
--explain-failures --ai-provider ollama --ai-model MODEL`. This intentionally
simulates an FTP login refusal through the ordinary transport code. Its report
is marked as a simulation; code determines `fail` and the expected exit code is
1. The report is not added to hardware or offline regression history, and the
model receives only sanitized failure evidence. The Development Test Lab's
**Test local AI (simulation)** button runs the same probe and asks only the
configured local Ollama model for an explanation. It never contacts a C64U or
sends probe evidence to the cloud.

The `Argonaut Test Lab` GitHub workflow runs this offline suite and the unit
tests for pushes and pull requests targeting `development`. It keeps the JSON
report as a workflow artifact and requires no C64U, credentials, GUI, or AI
service. Hardware checks remain local and opt-in.

The same command can run headlessly against hardware with
`python3 -m c64u_browser.test_lab --suite hardware`. This flag uses only the
selected **Argonaut Development** profile. It runs the read-only hardware suite,
saves a private report, and prints sanitized JSON with the comparison result.
If the device password is needed, `--password-stdin` reads one line from
standard input; no password is accepted as a command-line argument or stored
in preferences. `--timeout N` sets a 1–30 second hardware timeout. Exit codes
are 0 for pass, 1 for fail, 2 for skip, and 3 for startup or history errors.
An all-skipped run is kept for audit but is ignored as a comparison baseline.
`--device-id ID` can target a specific C64U through its already saved,
identity-bound Argonaut Development profile instead of the currently selected
profile. A missing or ambiguous match stops before any device read. The device
ID and host are excluded from JSON output; each profile keeps its own hardware
history. The same option works with the headless monitor.

`python3 -m c64u_browser.test_lab_fleet` runs one read-only pass across every
identity-bound **Argonaut Development** connection. Unbound connections are
ignored. Its JSON output contains a separate result and exit code for each
profile under a stable, opaque key; no profile name, device ID, or host is
included. Overall failure wins over passing or skipped profiles. A startup or
history error stops the pass. The monitor can repeat this fleet pass with
`--all-profiles`, still waiting after each completed pass and never running
two passes concurrently. The same password line, if supplied with
`--password-stdin`, is used for every profile during that process session.

For unattended failure explanations, add `--explain-failures --ai-provider
ollama --ai-model MODEL` to either suite. A downloaded local Ollama model must be
running on this computer. `--ai-provider openai` explicitly selects the cloud
adapter and requires `OPENAI_API_KEY` in the process environment. A passing run
does not contact either model. On a failed run, the command adds a separate
`analysis` object to its JSON output; AI service errors appear there as
`status: error`. The saved report, deterministic verdict, and exit code are
unchanged even if the model is unavailable. Neither the key nor model text is
stored in the private run history.

A saved or exported report can also be analyzed later, without reconnecting to
the C64U or rerunning checks:
`python3 -m c64u_browser.test_lab_replay --report REPORT.json --ai-provider
ollama --ai-model MODEL`. The same command accepts `--ai-provider openai` for
explicit cloud analysis. It validates the saved verdict before use and prints
only the report status and a separate analysis object. Its exit code remains 0
for a saved pass, 1 for a saved failure, 2 for an all-skipped report, and 3 for
an unreadable or damaged report. A passing or skipped report never contacts a
model. The input report is never changed.

For a monitor that runs independently of the Argonaut window, use
`python3 -m c64u_browser.test_lab_watch --interval-minutes 30`.
It immediately runs the same read-only hardware suite for the selected
Argonaut Development profile, then waits 30 minutes **after each completed
run** before starting the next. It never catches up missed intervals or runs
checks concurrently. `--runs N` limits the session for testing; without it,
the process continues until interrupted. Output is one JSON object per line,
with a run number, the ordinary test exit code, and the sanitized report.
Setup or history errors stop the monitor. A failed check is recorded and the
next scheduled run still occurs. If needed, `--password-stdin` reads one
password line once and keeps it only in this process's memory for the session.
AI options match the one-shot command and remain opt-in; passing runs do not
contact a model. The monitor is not started automatically by installing
Argonaut.

On Linux, `packaging/linux/test_lab_timer.py` renders a user-level systemd
service and timer for unattended Development fleet checks. The service calls
the same ordinary read-only fleet command through a separate desktop-alert
layer and saves reports under the private Development history. It treats an
all-skipped run as a nonfailure and a failed check as a service failure; AI
analysis is off by default. The alert layer keeps a private state containing only
opaque profile keys and stable check IDs. It shows a local desktop notification
for a new or changed failure and when confirmed passing checks recover.
Unchanged failures do not repeat the notification, and skipped checks do not
claim recovery. An unavailable desktop notification leaves the verdict and
saved reports intact and will be retried on the next run. The timer waits five
minutes after it is enabled, then starts a new run 30 minutes after the last
start. It does not try to catch up missed runs. The user service runs while
the user's systemd manager is active; it does not enable login lingering.
Stopping and disabling `argonaut-test-lab-fleet.timer` ends unattended runs
without deleting saved reports.

The Development Debian package includes this fleet service and timer with a
package-local launcher. Test Lab shows its state separately as **Background
C64U checks**. **Enable checks** starts the persistent 30-minute schedule, and
**Stop checks** disables it without deleting reports or AI diagnoses. The
nearby **Run C64U checks every 30 minutes while this window is open** switch is
the temporary in-app schedule; its label deliberately distinguishes the two.

In the Development Test Lab tab, **Explain unattended C64U failures with local
AI** can be enabled with the name of a downloaded Ollama model. **Save local AI
setting** writes a private local-only setting; the existing user timer reads it
on its next fleet run without a restart. Cloud models and Ollama `:cloud` models
are refused for unattended analysis. A failed report is analyzed only after
the ordinary tests have determined and saved its verdict. Passing and skipped
runs never call a model.

A new or changed saved failure can add a short local diagnosis preview to its
desktop alert. The bounded full diagnosis is kept separately in a private
`latest-local-ai.json` file under Development's Test Lab settings. Opening the
matching saved result in the Development Test Lab shows the full diagnosis. Up
to 20 private diagnoses are also retained in `local-ai-diagnoses`, so an
older saved failure can still show its explanation and a recurring failure can
reuse it without another model call. The diagnosis never changes the saved test
report or fleet exit code. Identical sanitized failure evidence reuses that
diagnosis instead of calling the model repeatedly. If
Ollama is unavailable, Argonaut shows the ordinary failure alert and retries
diagnosis on the next failed run. When a retry succeeds, it sends one local
diagnosis-ready alert. Saving the switch off in the Development Test Lab tab
disables unattended AI analysis. The unattended layer analyzes at most four
failed C64Us per run; larger fleets keep the ordinary saved results and alerts.
Local requests allow up to 60 seconds per failed C64U and cap the diagnosis at
256 generated tokens so the unattended service remains bounded.

The simulated checks exercise the real REST and FTP transport code against
in-process fixtures. They cover valid and malformed REST responses, REST and
FTP authentication failures, FTP MLSD listings, and the LIST fallback. Each
fixture is isolated to its check; transport fixtures record exactly one
operation.
The identity regression fixture simulates an address that answers as a different
C64U. It checks that Argonaut reports an identity failure and skips all later
drive, storage, and version reads; that fixture records only the two initial
identity reads.
The complete hardware fixture runs the same four read-only checks against
simulated REST and FTP responses, including bound identity, both drive states,
the FTP root listing, and a stable API version. It records the expected five
transport operations without opening a network connection.
Four transfer fixtures exercise the real FTP download and upload code against
an in-process server object. They prove a complete download and verified upload,
cleanup after an interrupted download, and refusal to connect when an upload
destination already exists. Their result events remain sanitized and marked as
simulations; none writes to a C64U.

The development tab also offers **Run C64U checks**. This opt-in suite uses the
current connected profile and performs only read-only identity/firmware, drive
status, FTP root listing, and API version checks. It does not change settings,
drives, machine state, or files. A disconnected app or a profile without a bound
device identity produces skipped checks without opening a network connection.
If the bound identity fails, dependent checks skip instead of probing that
device further. A connection that fails during an opted-in run is a test failure.
The **Run C64U checks every 30 minutes while connected** switch schedules the
same suite for this app session only. It waits for a bound, connected device
and an idle app; after an offline period it runs once on reconnection rather
than trying to catch up missed intervals. Scheduled runs use the same private
history, comparisons, and optional AI failure explanations. The switch is off
by default and is cleared when Argonaut closes.

Each check has a stable ID, a title, a pass/fail/skip result, an error category,
timing, and structured C64U operation events captured while it ran. REST calls,
FTP directory browsing, uploads, downloads, Flash reads and writes, file
actions, replacement, and DMA actions emit the same event format. REST targets
use recognized route labels; dynamic configuration segments and URL query
values are redacted. FTP file and entry targets are generic labels. Assertions
and exceptions determine the result. Exception messages, credentials, request
bodies, URL query values, and device file paths are excluded from reports.
Development also keeps ordinary C64U operation events in a private, rotating
JSONL activity log under its settings folder while the app is open. The log is
limited to 1 MB plus two rotated backups and does not include credentials,
request bodies, dynamic route segments, query values, or file paths. Test Lab
reports and headless fleet runs keep their own private histories separately.
Offline fixture events are marked as simulations and remain in their Test Lab
reports without appearing in the ordinary activity log.
The runner rejects missing, invalid, or duplicate check IDs before running any
check. History comparison ignores damaged saved reports and rejects inconsistent
overall verdicts, so a duplicate ID cannot overwrite a failure in the baseline.
The runner also records `skip` separately when a check cannot run. Offline and
hardware runs use separate comparison baselines. Hardware history is also
partitioned by the saved connection profile, so two C64Us cannot become each
other's regression baseline. The private folder name is a hash of the profile
ID; the ID and host are absent from the report. Existing unscoped hardware
reports are preserved, but each profile starts a new baseline on its first
scoped run.
The built-in checks use explicit assertions that remain active when Python runs
in optimized mode. Operation events from unrelated threads are excluded from
each check's report.

The Developer Mode UI displays these reports. Any future hardware checks that
change device state will need explicit setup and cleanup. An AI analysis
service can read the same
report to explain failures, but must never decide whether a check passed. That
service should sit behind a separate gateway for local or cloud models; a C64
PETSCII client can use the gateway later without entering the test runner.

Opening the Development Test Lab tab loads the latest saved hardware result
for the first profile needing attention, or the selected profile when all are
passing. The saved C64U row shows each bound profile's most recent result.
When the most recent run skipped, it also shows the last verified verdict so
an earlier failure is still visible. **View latest saved result** and **View
last verified result** let you inspect the deterministic check details for a
chosen C64U, including reports written by the unattended Linux service. A
verified saved result also shows new and resolved check failures relative to
that C64U's prior verified run. A skipped run cannot confirm recovery and does
not get a regression comparison. **Saved runs** lists up to 20 retained
results for the selected C64U by save time. **View selected run** opens any of
them with the comparison against its own prior verified run and its matching
saved local AI diagnosis, if one exists.
**Refresh saved results** loads newly written unattended reports while the
Test Lab tab remains open.

The AI analysis boundary extracts only failed checks and a small whitelist of
sanitized operation fields. It rechecks route, operation, target, outcome, and
error labels before sending evidence to a model. Built-in check IDs are known
safe labels; an unknown check ID is replaced with an opaque failure number in
model evidence. Check titles, exception messages, and extra report fields are
excluded, and analysis refuses more than 32 failures rather than sending a
partial or oversized explanation. The AI Gateway supports local
Ollama chat and the OpenAI Responses API; each returns a diagnosis as a separate
object. This object
cannot change the saved report, its code-determined verdicts, or the run
comparison. Model responses are bounded and treated as suggestions.
Both providers implement the same gateway adapter contract: bounded sanitized
evidence in, diagnosis text or a stable categorized error out. Provider response
shapes are validated inside their adapters, so a malformed local or cloud reply
cannot escape into the deterministic test runner as an unrelated exception.

In the development Test Lab tab, choose **Local Ollama** or **OpenAI cloud** and
enter a model name. Ollama must be running locally with a downloaded model.
The local option rejects Ollama's `:cloud` model names.
OpenAI cloud requires `OPENAI_API_KEY` in Argonaut's environment; the key is
never written to the report or preferences. Cloud analysis sends only the
failed-check evidence, not the full report. OpenAI requests set `store: false`.
**Explain failures** analyzes the current failed run. The optional **Explain
failed runs automatically** switch applies only to this app session; turning it
on with OpenAI cloud selected sends future failed-run evidence to OpenAI.
Passing reports do not call a model.

The C64 AI bridge status is also determined without a model. Test Lab checks
the managed bridge process, verifies that its saved listener address still
belongs to this computer when the process is stopped, reads Ollama's bounded
local model list, and distinguishes an unavailable service from a missing
configured model. These operational health states remain separate from C64U
test verdicts and from AI-generated failure explanations.

The Linux Test Lab also provides **Test bridge AI** for an explicit end-to-end
readiness check. It uses the private bridge setting to send a fixed question
through the same authenticated compact protocol used by the C64 client.
Ordinary code verifies the reply framing, bounded length, completeness, and
printable ASCII. It does not judge the model's wording, and it does not display
or retain the response text.

API contracts: [Ollama chat](https://docs.ollama.com/api/chat),
[Ollama nonstreaming](https://docs.ollama.com/api/streaming), and
[OpenAI Responses](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

Development builds now include a Test Lab tab. It runs the offline and simulated
checks on the application's worker thread, shows each result and its operation
events, and exports the sanitized JSON report to a local file chosen by the user.
Each run is also saved privately under the development settings directory.
Argonaut keeps the newest 20 reports and compares check verdicts by stable ID
to show new failures, resolved failures, and added or removed checks. A failed
history write does not change the check verdict or prevent JSON export.
