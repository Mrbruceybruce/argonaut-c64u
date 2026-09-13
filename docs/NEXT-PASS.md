# Next development pass

## Mount & Run

Implemented locally; hardware validation pending. Mount & Run sits beside Mount in the Drive A card on the Drives tab.
Use the selected C64U image path. Initial support is D64 only and requires
the C64U DMA service. Firmware's network command runs a temporary copy on
Drive A; the UI must explain that the original image and selected mount
write mode are not used for persistence by this operation.
Validate transfer, authentication, error handling, and behavior on hardware
before release. Do not implement this feature in the current stable release.

## Development setup

Keep installed stable Argonaut separate from development. Recommended next
setup: a persistent Git checkout and development branch, a clearly marked
About/build identifier, and separate development profiles/preferences so
testing does not alter stable settings. GitHub Actions remains the package
builder for Windows and macOS.
