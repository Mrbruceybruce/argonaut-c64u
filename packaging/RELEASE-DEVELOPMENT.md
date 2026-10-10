# Argonaut Development — 1.10

This is the current 1.10 Development channel, not a Stable 1.10 release.
Stable remains 1.9. The next local Debian package is `1.10~dev2`; About and
the application-menu entry display `1.10-dev2` with the packaged source identity.
Source Development displays `1.10-dev` and its checkout identity.

Install the separately approved local Debian Development package, then launch
`argonaut-development` or its **Argonaut Development** application-menu entry.
For source work use `./run-development`. The authoritative local build procedure
is in `docs/RELEASING.md` in the source checkout; package installation and acceptance
are separate approval steps.

Development has separate package, application, preferences and service identities.
Passwords are session-only; it does not access installed Stable keyring entries.
Closing the application clears session credentials. Device operations still affect
the connected hardware, so channel isolation is not a device sandbox.

This checkpoint includes the published navigation/session-safety and contextual
operation-status/cancellation improvements. Streaming remains OPEN / intermittent /
instrumented; packaging does not qualify or fix it. The shared historical
`1.8-replay.3` workflow is not the current 1.10 build procedure.

No public 1.10 tag or release is implied. Cross-platform release qualification and
public-release review of Commodore branding remain pending. Its SVG and separate
attribution/license text are included alongside the other application assets.
