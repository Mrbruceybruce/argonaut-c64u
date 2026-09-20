# Server-first development policy

**Argonaut Core is the product. GTK, PWA, CLI, automation, and PETSCII
programs are clients.**

Argonaut Core is the headless application layer that owns C64 Ultimate state
and operations. It includes discovery, connection and authentication, profiles,
file transfer, machine and settings control, structured logging, deterministic
Test Lab behavior, and eventually the AI Gateway. A user interface presents
these capabilities; it does not reimplement their rules.

## Core and client boundary

- Core owns device profiles, credentials, discovery, connection testing,
  identity binding, active sessions, reconnect rules, and every C64U operation.
- Clients own presentation, interaction state, window layout, and preferences
  that apply only to that client. Core settings and state are stored separately
  from client settings and state.
- Clients must not construct or receive a raw `UltimateClient`. Transport
  clients and credentials remain private implementation details of Core.
- Every new capability must first have a headless Core interface. Core must be
  usable and testable without GTK, a display server, or a specific client.
- Core operations return ordinary typed or structured data, events, progress,
  and sanitized categorized errors. They do not return GTK objects, widgets,
  dialogs, or transport implementation objects.
- Credentials enter Core through a credential provider or an explicit
  connection request. They are never returned to clients, included in events,
  logged, or embedded in operation results.
- Long-running operations use jobs with stable identifiers, progress events,
  explicit cancellation, and structured final results. A client closing must
  not silently corrupt or ambiguously abandon a Core operation.
- Device concurrency is explicit. Core serializes or rejects conflicting work
  for one C64U and defines how independent devices may run concurrently.
  Destructive operations require an explicit reviewed intent and Core-level
  safety checks; a client confirmation dialog alone is not a safety boundary.
- Stable and Development Core instances remain isolated. They use separate
  configuration, credentials, state, logs, jobs, and service identities so a
  development client cannot attach accidentally to a stable Core instance.

## Interfaces and transport

Core's application interface is independent of process boundaries. The GTK
application may instantiate it in-process during migration. A persistent server
will later host the same interface.

Network transport is not Core. HTTP and WebSocket will be adapters around the
same Core operations, results, events, jobs, and errors. The future PWA, CLI,
automation tools, and PETSCII client will use those adapters without changing
where device rules or state live.

## Filesystem ownership

Every Core file reference identifies its filesystem explicitly. `core-host`
paths belong to the machine running Core, `c64u` paths belong to the active C64
Ultimate, and future `client-upload` references will identify files staged by a
requesting client rather than paths on that client's machine. An arbitrary path
sent by a PWA or other remote client must never be interpreted as a Core-host
path. The in-process GTK client may select `core-host` paths because it currently
runs on that same machine; this is a deployment fact, not a permanent API
assumption.

During incremental migration, a narrow in-process compatibility service may
adapt existing desktop workflows to Core-owned sessions. It must not reveal the
underlying `UltimateClient` or credentials, and it should shrink as dedicated
Core capabilities replace it. Working features move across this boundary in
reviewable sections; server-first development does not require a rewrite.

## Device scheduling and job lifecycle

Core, rather than a client worker, decides when device operations execute.
Operations for one physical C64U use an ordered FIFO lane and are serialized
unless a capability documents a narrower safe concurrency rule. Different
physical-device lanes may coexist. Core-host-only file work uses its own ordered
lane and may coexist because it has no device transport or state.
Job identity, physical-device identity, and connection-session identity are
separate. Every device job is bound to both the device and the session captured
when it was submitted. Reconnecting to the same physical C64U creates a new
session; queued work from the old session fails safely and must be prepared
again rather than silently crossing the reconnect.

Completed jobs are retained for a bounded time and count so clients can collect
their final structured result. Queued and running jobs are never evicted.
Unused confirmation plans expire and their registries are bounded; consumed,
expired, or evicted plans cannot be reconstructed by a client and require a new
preview. Jobs and plans are currently process-local and do not survive a Core
restart. Persistent job storage remains a later server-hosting decision.

## Required checks

Each Core capability needs deterministic headless tests for its contract,
errors, state transitions, and safety rules. Client tests cover presentation and
translation into that contract. At least one test must ensure Core imports and
runs without importing GTK or opening a display.
