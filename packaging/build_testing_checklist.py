#!/usr/bin/env python3
"""Build a versioned ODS physical-test checklist from the styled template."""
import argparse
from pathlib import Path
import tempfile
from xml.sax.saxutils import escape
import zipfile


TEMPLATE_VERSION = '1.7-disk.14'
TEMPLATE_COMMIT = 'b15f6ab8d64796692dbcdca3ef6bf788b0528300'
TEMPLATE_INSTRUCTIONS = ('Complete every numbered task. Select a result and '
                         'record observations in the Comments box on the same row.')
TEMPLATE_TASKS = (
    'Confirm About shows 1.7-disk.14 and the source commit shown for this release.',
    'Confirm the settings tab is labeled Ultimate Menu. Close Preferences and confirm keyboard focus returns to the main Argonaut window.',
    'Open a supplied disk fixture and choose Extract selected…. Confirm the chooser opens in the folder shown in the local Files pane. Complete the extraction and confirm the new file appears selected without a manual refresh. Close the disk directory and confirm focus returns to Argonaut.',
    'On the C64U side of Files, right-click a D64, G64, D71, G71, or D81 and choose Mount…. Confirm Drives opens with the complete image path prepared for Drive A. Confirm no mount occurs until the existing review is accepted.',
    'Open the supplied Test Disk Images D64, D71, and D81 fixtures. Confirm each directory opens, validates, reports free blocks, and extracts its large test file. Confirm the D81 CBM entry is labeled as a partition and cannot be opened as a folder.',
    'On copied standard D64, D71, and D81 images, stage a rename and add a small PRG. Use Save as… for each and confirm the chooser opens in the folder currently shown in the local Files pane. Reopen each output and confirm both changes. Cancel another staged edit and confirm the source remains unchanged. Confirm the D81 CBM partition cannot be removed.',
    'Create a blank D64 with a chosen label and two-character ID. Reopen it and confirm it validates, has no files, and reports 664 blocks free.',
    'Open the supplied REL D64 fixture, remove its REL entry, save it under a new name, and confirm the result validates and reports 664 blocks free. On a C64U directory listing, confirm RELTEST and RELFILE use normal readable characters.',
    'Copy one item between the local and C64U panes with Copy/Paste, then another with drag-and-drop. After each success, confirm both the source item and new destination copy remain selected.',
    'In the local Files pane, confirm hidden files are initially absent. Enable Preferences → General → Show hidden local files and folders, confirm they appear, then disable it and confirm they disappear.',
    'Connect to a C64U at BASIC READY. In Streams, enter PRINT "ONE" and press Return, then enter PRINT "TWO" without clicking the input again. Confirm each command sends, the field clears, and focus remains ready for the next line. Video preview is not required.',
    'Run Run offline checks in Test Lab and confirm every check passes. Connect the C64U, run Run C64U checks, and confirm all read-only checks pass.',
    'Check upload/download, Ultimate Menu, Drives, video/audio preview, screenshot, recording, Mount & Run, Preferences persistence, and Quit.',
)

TEMPLATE_AREAS = (
    'Build identity', 'Preferences', 'Disk extraction', 'Remote mount',
    'Disk reading', 'Disk editing', 'Blank D64', 'REL removal', 'File copying',
    'Hidden files', 'Streams input', 'Test Lab', 'Core regression',
)

AREAS = (
    'Build identity', 'Preferences recovery', 'Files focus and local D64',
    'Disk directory controls', 'Multiple file addition', 'C64U D64 creation',
    'Disk format regression', 'Remote mount', 'File copying', 'Hidden files',
    'Instant replay', 'Test Lab', 'Core regression',
)

TASKS = (
    'Confirm About shows {version} and source commit {commit}.',
    'Open Preferences with any previously saved screenshot or recording folder unavailable. Confirm Close and the window close button close Preferences immediately without requiring Restore defaults. Enter a new nonexistent folder and confirm Argonaut rejects it.',
    'In Files, click each pane and confirm its Active label and border move with keyboard focus while the inactive selection becomes subdued. Create a local blank D64 and confirm it refreshes and selects the new image without opening its directory. Repeat that filename and confirm Create is disabled with visible red feedback.',
    'Open a D64 directory. Confirm Extract, Add, Rename, and Remove show clear icons with identifying tooltips; Discard changes and Save image as… are separate at the right; the title does not show an I-beam; and unsaved staged changes still require confirmation before closing.',
    'Choose Add file… and confirm the chooser starts in the local Files folder. Select at least two small host files at once and confirm one review table shows every file with an editable C64 filename and type. Include text and tokenized $0801 .bas files and confirm they default to SEQ and PRG respectively. Confirm the batch once, save it, reopen it, and verify every file.',
    'In the C64U Files pane, choose New D64 disk on C64U…. Create a unique image and confirm Argonaut refreshes, selects, reads back, and validates an empty standard 35-track D64 with 664 blocks free. Repeat the name and confirm the existing image is protected.',
    'Open the supplied D64, D71, D81, and REL fixtures. Confirm each directory validates, reports the expected free blocks, and extracts a file. Confirm D81 CBM partitions remain protected and REL removal reclaims its data and side sectors.',
    'On the C64U side of Files, right-click a D64, G64, D71, G71, or D81 and choose Mount…. Confirm Drives opens with the full path prepared for Drive A and no mount occurs before review is accepted.',
    'Copy one item between local and C64U panes with Copy/Paste, then another with drag-and-drop. Confirm source and destination copies remain selected and the destination pane becomes visibly active when focused.',
    'Confirm hidden local entries are absent by default. Enable Preferences → General → Show hidden local files and folders, confirm they appear, then disable it and confirm they disappear.',
    'Confirm instant replay is off by default. Enable the 30-second instant replay in Preferences, start an audio preview, and wait at least 35 seconds. Confirm Streams reports about 30 seconds retained. Start an ordinary recording, save the recent replay while recording continues, then stop recording. Play both WebM files and confirm video and audio. Stop preview and confirm replay history clears.',
    'Run offline checks and connected read-only C64U checks in Test Lab. Confirm ordinary-code verdicts complete and any optional AI text does not change those verdicts.',
    'Check upload/download, Ultimate Menu, Drives, video/audio preview, screenshot, recording, Streams Return-to-send, Mount & Run, Preferences persistence, disconnect/reconnect, and Quit.',
)


def build(template, output, version, commit):
    replacements = {old: new.format(version=version, commit=commit)
                    for old, new in zip(TEMPLATE_TASKS, TASKS)}
    replacements.update(dict(zip(TEMPLATE_AREAS, AREAS)))
    replacements.update({
        f'Argonaut {TEMPLATE_VERSION} testing checklist':
            f'Argonaut {version} testing checklist',
        TEMPLATE_VERSION: version,
        TEMPLATE_COMMIT: commit,
        TEMPLATE_INSTRUCTIONS:
            ('Complete every numbered task. Select a result and record observations '
             'in the Comments box on the same row. Save and return the completed ODS '
             f'as Argonaut-{version}-testing-results-PLATFORM-TESTER.ods.'),
    })
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(template) as source:
        content = source.read('content.xml').decode('utf-8')
        styles = source.read('styles.xml').decode('utf-8')
        for old, new in replacements.items():
            encoded_old = escape(old, {'"': '&quot;'})
            needle = '<text:p>' + encoded_old + '</text:p>'
            if needle not in content:
                raise ValueError('Checklist template text was not found: ' + old[:60])
            content = content.replace(
                needle, '<text:p>' + escape(new, {'"': '&quot;'}) + '</text:p>')
        styles = styles.replace(
            'style:print-orientation="portrait"',
            'style:print-orientation="landscape" fo:page-width="11.6929in" '
            'fo:page-height="8.2677in"').replace(
            'style:scale-to="100%"', 'style:scale-to-pages="2"')
        with tempfile.NamedTemporaryFile(
                dir=output.parent, suffix='.ods', delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            with zipfile.ZipFile(temporary_path, 'w') as destination:
                for item in source.infolist():
                    if item.filename == 'content.xml':
                        data = content.encode('utf-8')
                    elif item.filename == 'styles.xml':
                        data = styles.encode('utf-8')
                    else:
                        data = source.read(item)
                    destination.writestr(item, data)
            temporary_path.replace(output)
        finally:
            temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--template', default=str(
        Path(__file__).with_name('testing-checklist-template.ods')))
    args = parser.parse_args()
    build(args.template, args.output, args.version, args.commit)


if __name__ == '__main__':
    main()
