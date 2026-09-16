# Argonaut 1.5-ai.1 — AI and Test Lab development testing

This build starts from stable Argonaut 1.5 and keeps Development profiles,
preferences, reports, and build identity separate from the installed stable app.

The Development Test Lab now includes:

- deterministic offline, simulated, and read-only C64U checks with structured
  operation evidence and retained regression history;
- optional failure-only AI explanations through local Ollama or OpenAI, kept
  separate from code-determined verdicts;
- opt-in unattended read-only checks for every identity-bound Development C64U,
  changed-failure and recovery notifications, and bounded local AI diagnoses;
- a paired local C64 AI bridge and interactive USB2 PETSCII client;
- deterministic bridge, network, Ollama, and downloaded-model health checks;
- separate controls for five-minute AI health alerts, persistent 30-minute fleet
  checks, and the temporary schedule that runs only while the window is open.

The Debian Development package includes the local bridge, health monitor, and
fleet-check user services. Ollama, a downloaded model, and the narrow TCP 6464
firewall rules for paired C64U addresses remain explicit prerequisites. The
pairing token and saved diagnostic material stay private and are not committed.

Windows: extract the portable ZIP to a writable folder and run `Argonaut.exe`.
Mac: open the DMG and copy Argonaut Development.app to Applications, or extract
the ZIP. Apple Silicon and Intel packages require macOS 15 or newer. The Mac app
is ad-hoc signed, not notarized. If blocked, use System Settings → Privacy &
Security → Open Anyway. Linux background-service controls require systemd and
will report unavailable on other platforms.

## Test checklist

1. Confirm About shows 1.5-ai.1 and the expected source build identifier.
2. Connect each C64U and run **Run C64U checks**. Confirm all four read-only
   checks pass and saved runs remain selectable after restarting Argonaut.
3. Run **Test local AI (simulation)**. Confirm the expected FTP failure appears
   and the diagnosis explicitly identifies it as a fixture, not a device fault.
4. On Debian, confirm the C64 AI bridge, automatic health alerts, and background
   C64U checks all show **On**. The temporary checkbox must say it applies only
   while the window is open.
5. Launch the paired C64 AI client on each C64U and ask one short question. Check
   that the reply appears on the C64 and the prompt returns.
6. Stop and restore Ollama once. Confirm Test Lab reports the model outage and
   later recovery without changing any saved C64U verdict.
7. Check file copy, Settings, Drives, Send Text, screenshot/recording, Mount &
   Run, and Quit as stable 1.5 regression checks.

Operations still affect the connected real C64U and its files. The hardware
suite itself is read-only. Mount & Run requires the DMA network service. The
C64 AI launcher can enable Command Interface for the current runtime but does
not save the C64U configuration to flash. This prerelease does not replace the
stable 1.5 installation.
