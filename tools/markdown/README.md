# Offline Markdown validation

P4-3 adds an independent Test Lab job on the existing development push, pull
request and manual triggers. It does not change the seven P4-2 executions or
qualify the deferred GTK regression. No hardware or external destinations are
contacted by validation.

## Policy

The NUL-delimited `git ls-files -z` inventory selects tracked `.md` and
`.markdown` files case-insensitively. Untracked files cannot satisfy links.
Relative paths resolve from the document; `/` paths resolve from the repository
root. Tracked directories are valid destinations. Paths require exact case.
Percent escapes must be valid UTF-8. Repository escape and all symlink traversal
are rejected, including symlink Markdown sources. Query strings do not affect
local file lookup. Fragments are checked on Markdown targets; fragments on
other file formats are not interpreted.

Pinned remark-parse and remark-gfm parse links, images, reference definitions,
inline text and ATX/Setext headings. Pinned github-slugger supplies Unicode,
punctuation and duplicate-heading behavior. HTML IDs and named anchors are
recognized in parsed HTML outside comments. Raw HTML href/src attributes are
not Markdown links and are not validated. HTML entity decoding in raw anchor
attributes and browser DOM behavior are outside this validator's scope.

Full, collapsed and shortcut references are validated only when the parser
recognizes them and resolves their definitions. Unresolved reference-like text
remains prose, including full/collapsed forms and image references. There is no
custom bracket scanner or unresolved-reference inference. Conflicting definitions
still fail, but unused definition destinations are not independently validated.
Code and comments are not scanned for link candidates. HTTP(S), protocol-relative
URLs and ordinary mailto links receive syntax checks only. Other schemes fail
unless covered by the archive or a narrow explicit exception. There are no DNS,
HTTP or availability checks.

Require UTF-8 without BOM and LF endings. Formatting uses exact-pinned
markdownlint 0.38.0 with only MD009, MD010 and MD047 enabled; all other rules are
off and inline configuration is disabled. MD009 uses `br_spaces: 2` and
`strict: false`; MD010 uses `code_blocks: false`; MD047 is enabled. No custom
whitespace or fence-closure inference supplements these rules.

MD009 allows two trailing spaces without requiring proof of a hard break and
ignores fenced/indented code contents. It still checks multiline inline-code
trailing spaces and fence delimiter lines. MD010 exempts code contents and inline
code, but checks fence delimiter lines. MD047 checks the terminal newline using
library semantics; empty files and extra final blank lines are allowed. No
line-length, heading progression, list marker, table alignment, language-label,
or fence-closure style is enforced. Parser interpretation determines which links
are recognized inside incomplete Markdown constructs.

## Archive and exceptions

[The roadmap archive](../../docs/ARGONAUT-ROADMAP-HISTORY.md) is parsed in full so
incoming heading links remain checked. Its editable provenance notice is checked
normally. The unique end-of-notice marker and following blank line delimit the
payload, whose SHA-256 must equal
`ef1427eee43129f8224e767115121464ba0189462fe29ad8c84d12e9ffb72c9f`.
Outgoing links and style findings inside that payload are reported as historical,
not errors. Hash/boundary failures cannot be excepted. This preserves historical
claims as evidence; it does not make them current planning authority.

`policy.json` has no general exceptions. A future exception must specify exact
`path`, `rule`, `destination`, `line`, and a nonempty `reason`. Matches remain in
the report with severity `exception`; unused exceptions fail. Never add an
exception merely to conceal a false positive. Stop and report policy conflicts;
do not repair existing documentation as part of this change.

## Execution and evidence

The Dockerfile pins the official Node 22.14.0 Bookworm slim manifest digest.
Only package metadata enters the build context. `npm ci --ignore-scripts`
acquires locked dependencies before isolated execution. Changing pins requires
review and rerunning the synthetic suite and repository checks.

The workflow exports a tracked working-tree snapshot using the NUL inventory,
without Git metadata or untracked fixtures. The runtime is nonroot, network-none,
read-only, capability-free, with no privilege escalation, one CPU, 512 MiB memory,
64 processes, and 128 MiB temporary space. Only its results directory and scratch
are writable. Tests and two validation runs execute within a 240-second bound.
The second JSON must match the first byte-for-byte.

JSON includes the document inventory, sorted diagnostics and error count.
Diagnostics carry path, one-based line/column, rule, severity, message and
destination. Reference-use failures include definition locations. Text quotes
paths/destinations to prevent control-character injection; GitHub annotations
escape percent, newline, comma and colon as appropriate. Exit codes are 0 for
success, 1 for findings, and 2 for execution failure. Historical findings and
explicit exceptions are visible without changing the failure count.

The always-run cleanup step inspects and removes labeled containers and verifies
absence. Interrupted creation leaves a pending marker, triggers repeated cleanup,
and fails closed even if no container is found. Daemon failure or whole-runner
loss cannot guarantee cleanup; artifacts preserve available evidence. JSON,
logs, test TAP, image/container settings and cleanup evidence upload even on
failure, with 14-day retention. Acquisition and artifact upload use the network;
validation itself does not.

For a local functional check, install dependencies in a disposable tooling copy
with `npm ci --ignore-scripts --no-audit --no-fund`, then run:

```sh
node --test check.test.mjs
node check.mjs --root /path/to/repository --json /tmp/markdown-results.json
```

That direct invocation is not isolation qualification. In constrained environments,
create an inventory with `git ls-files -z` and pass `--inventory /path/to/inventory`.
The supplied inventory is trusted input and must originate from the same checkout.
Use the workflow's container recipe to establish network/mount/resource isolation.
New tooling files remain untracked during review; the existing baseline has 42
Markdown documents. A temporary review snapshot may include the seven proposed
new files to check the additional tooling README without staging the real index.
