import {test} from 'node:test';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {validate, annotation} from './check.mjs';

function fixture(t, content, policy = {}, untracked = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'markdown-test-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  for (const [p,s] of Object.entries({...content,...untracked})) {
    fs.mkdirSync(path.dirname(path.join(root,p)), {recursive:true});
    fs.writeFileSync(path.join(root,p), s);
  }
  return {root, run:() => validate(root, Object.keys(content), policy)};
}
const rules = r => r.diagnostics.filter(d => d.severity === 'error').map(d => d.rule);
test('relative, root, directory, images, encoded punctuation, nested parentheses', t => {
  const f = fixture(t, {'a.md':'[root](/d/B.md#title) [dir](d/) ![image](d/a%20b.png) [nested](d/a(b).png)\n','d/B.md':'# Title\n','d/a b.png':'','d/a(b).png':''});
  assert.equal(f.run().errors, 0);
});
test('Unicode, inline rendered text, setext, repeated hyphens and duplicate collisions', t => {
  const f = fixture(t, {'a.md':'# Héllo **World** `code`\n# A--B_c\n# Repeat\n# Repeat\n# Repeat-1\nSetext\n------\n[x](#héllo-world-code) [x](#a--b_c) [x](#repeat-1) [x](#repeat-1-1) [x](#setext)\n'});
  assert.equal(f.run().errors, 0);
});
test('HTML anchors and comments', t => {
  const f = fixture(t, {'a.md':'<a name="legacy"></a>\n<div id="custom"></div>\n<!-- <a id="hidden"></a> [x](missing) -->\n\n[x](#legacy) [x](#custom) [x](#hidden)\n'});
  assert.deepEqual(rules(f.run()), ['FRAGMENT']);
});
test('duplicate explicit IDs fail', t => assert.deepEqual(rules(fixture(t, {'a.md':'<a id="x"></a>\n<a id="x"></a>\n'}).run()), ['ANCHOR_DUPLICATE']));
test('case, untracked-only, missing image, fragment', t => {
  const f = fixture(t, {'a.md':'[x](B.md) [x](secret) ![x](missing.png) [x](b.md#no)\n','b.md':'# Yes\n'}, {}, {'secret':''});
  assert.deepEqual(rules(f.run()), ['PATH_MISSING','PATH_MISSING','PATH_MISSING','FRAGMENT']);
  assert.equal(f.run().diagnostics[0].column, 1);
});
test('escape, encoded escape and symlinks rejected', t => {
  const f = fixture(t, {'a.md':'[x](../outside) [x](%2e%2e/outside) [x](link)\n','link':''});
  fs.unlinkSync(path.join(f.root,'link')); fs.symlinkSync('/etc/passwd', path.join(f.root,'link'));
  assert.deepEqual(rules(f.run()), ['PATH_ESCAPE','PATH_ESCAPE','PATH_SYMLINK']);
});
test('source and directory symlinks rejected without reading outside', t => {
  const f = fixture(t, {'a.md':'[x](d/b.md)\n','d/b.md':'# B\n'});
  fs.rmSync(path.join(f.root,'d'), {recursive:true}); fs.symlinkSync('/tmp', path.join(f.root,'d'));
  assert.deepEqual(rules(f.run()), ['PATH_SYMLINK','PATH_SYMLINK']);
});
test('references: full, collapsed, shortcut, normalized labels, multiline definitions', t => {
  const f = fixture(t, {'a.md':'[Full][Some LABEL] [Some label][] [Some label]\n\n[some label]:\n  b.md#b\n  "title"\n','b.md':'# B\n'});
  assert.equal(f.run().errors,0);
});
test('conflicting definitions fail; unresolved reference-like text stays prose', t => {
  const f = fixture(t, {'a.md':'[x][missing] [x][] [ordinary prose] \\[escaped][literal]\n\n[a]: b.md\n[a]: c.md\n','b.md':'# B\n','c.md':'# C\n'});
  assert.deepEqual(rules(f.run()), ['REFERENCE_CONFLICT']);
});
test('reference diagnostics identify use and definition', t => {
  const r = fixture(t, {'a.md':'[x][ref]\n\n[ref]: missing\n'}).run();
  assert.equal(r.diagnostics[0].line,1);
  assert.match(r.diagnostics[0].message,/definition at 3:1/);
});
test('external syntax only, bare URLs, email and unknown schemes', t => {
  assert.equal(fixture(t, {'a.md':'https://unresolvable.invalid/a [x](https://no-dns.invalid/path) <a@example.invalid>\n'}).run().errors,0);
  const r = fixture(t, {'a.md':'[x](https:/bad) [x](ftp://host/path) [x](a%ZZ) [x](a%FF) [x](a%00)\n'}).run();
  assert.deepEqual(rules(r), ['URL_SYNTAX','URL_SCHEME','URL_SYNTAX','URL_ENCODING','URL_ENCODING']);
});
test('literal code and two-space hard breaks preserved', t => {
  assert.equal(fixture(t, {'a.md':'Hard break  \nnext\n\n```text\n\t[x](missing)   \n```\n\n    \t[x](missing)   \n'}).run().errors,0);
});
test('UTF-8, BOM, LF, final newline, tabs, accidental trailing whitespace', t => {
  assert.deepEqual(rules(fixture(t, {'a.md':Buffer.from([0xff])}).run()), ['UTF8']);
  const r = fixture(t, {'a.md':'\uFEFF# A\r\ntext\tX \nlast'}).run();
  for (const rule of ['BOM','LF','MD010','MD009','MD047']) assert.ok(rules(r).includes(rule));
});
test('fence closure is left to the parser, including nested blockquote/list', t => {
  for (const s of ['```\nx\n','> ```\n> x\n','- ```\n  x\n']) assert.equal(fixture(t, {'a.md':s}).run().errors,0);
  for (const s of ['~~~\nx\n~~~~\n','> ```\n> x\n> ```\n','- ```\n  x\n  ```\n']) assert.equal(fixture(t, {'a.md':s}).run().errors,0);
});
test('archive hash, boundary, incoming headings and historical outgoing/style', t => {
  const payload = '# Old\n[x](gone) \n';
  const policy = {archive:{path:'archive.md',boundary:'<!-- END -->\n\n',sha256:createHash('sha256').update(payload).digest('hex')}};
  const f = fixture(t, {'a.md':'[old](archive.md#old)\n','archive.md':'# Notice\n<!-- END -->\n\n'+payload}, policy);
  assert.equal(f.run().errors,0);
  assert.equal(f.run().diagnostics.length,2);
  assert.ok(f.run().diagnostics.every(d => d.severity === 'historical'));
  fs.appendFileSync(path.join(f.root,'archive.md'),'mutation\n');
  assert.ok(rules(f.run()).includes('ARCHIVE_HASH'));
  assert.ok(rules(fixture(t, {'archive.md':'# Old\n'}, policy).run()).includes('ARCHIVE_BOUNDARY'));
  assert.ok(rules(fixture(t, {'a.md':'# A\n'}, policy).run()).includes('ARCHIVE_MISSING'));
});
test('archive provenance notice is validated normally', t => {
  const payload = '# Old\n';
  const policy = {archive:{path:'archive.md',boundary:'<!-- END -->\n\n',sha256:createHash('sha256').update(payload).digest('hex')}};
  assert.ok(rules(fixture(t, {'archive.md':'[bad](missing)\n<!-- END -->\n\n'+payload},policy).run()).includes('PATH_MISSING'));
});
test('narrow documented exceptions and stale exceptions', t => {
  const policy = {exceptions:[{path:'a.md',rule:'PATH_MISSING',destination:'missing',line:1,reason:'Synthetic test only'}]};
  assert.equal(fixture(t, {'a.md':'[x](missing)\n'},policy).run().errors,0);
  assert.deepEqual(rules(fixture(t, {'a.md':'# A\n'},policy).run()), ['EXCEPTION_UNUSED']);
});
test('stable ordering and JSON, extra blank lines in P4-2 exception allowed', t => {
  const f = fixture(t, {'z.md':'[x](missing)\n','a.md':'# Exception\n\n\n\n[x](missing)\n'});
  assert.equal(JSON.stringify(f.run()),JSON.stringify(f.run()));
  assert.equal(f.run().diagnostics[0].path,'a.md');
});
test('GitHub annotations escape data and property injection', () => {
  const result = annotation({path:'x,\n::error::%.md',line:2,column:3,rule:'RULE',severity:'error',message:'bad\r\n::error::%',destination:''});
  assert.ok(!result.includes('\n'));
  assert.match(result, /x%2C%0A%3A%3Aerror%3A%3A%25.md/);
  assert.match(result, /bad%0D%0A::error::%25/);
});
test('inline literal tabs preserved', t => {
  assert.equal(fixture(t, {'a.md':'Use `a\tb` here.\n'}).run().errors,0);
});
test('inventory names with newline and Unicode remain distinct and deterministic', t => {
  const f = fixture(t, {'a.md':'[x](%C3%A9.md#ok)\n','é.md':'# OK\n','line\nbreak.md':'# Fine\n'});
  assert.equal(f.run().documents.length,3);
  assert.equal(f.run().errors,0);
});
test('archive integrity cannot be bypassed by a general exception', t => {
  const policy = {archive:{path:'a.md',boundary:'<!-- END -->\n\n',sha256:'bad'},exceptions:[{path:'a.md',rule:'ARCHIVE_HASH',destination:'',line:1,reason:'Not authorized'}]};
  assert.ok(rules(fixture(t, {'a.md':'<!-- END -->\n\n# Old\n'},policy).run()).includes('ARCHIVE_HASH'));
});
test('CLI defect exits nonzero and writes JSON with exact location', t => {
  const f = fixture(t, {'a.md':'# Good\n\n[x](missing)\n'});
  const list = path.join(f.root,'inventory'), out = path.join(f.root,'result.json');
  fs.writeFileSync(list,'a.md\0');
  const child = spawnSync(process.execPath, [fileURLToPath(new URL('./check.mjs', import.meta.url)), '--root', f.root, '--inventory', list, '--json', out, '--github'], {encoding:'utf8'});
  assert.equal(child.status,1,child.stderr);
  const finding = JSON.parse(fs.readFileSync(out)).diagnostics.find(d => d.rule === 'PATH_MISSING');
  assert.equal(finding.line,3); assert.equal(finding.column,1);
  assert.match(child.stdout,/::error file=a.md,line=3,col=1/);
});

test('angle destinations preserve parsed spaces in links, images and definitions', t => {
  const r = fixture(t, {'a.md':'[x](<a b.md#some heading>) ![x](<a b.png>) [x][ref]\n\n[ref]: <a b.md>\n','a b.md':'<a id="some heading"></a>\n','a b.png':''}).run();
  assert.equal(r.errors, 0);
});
test('angle destinations still reject malformed URLs and enforce exact inventory', t => {
  const r = fixture(t, {'a.md':'[x](<https://bad host/a>) [x](<https:/bad>) [x](<a %ZZ.md>) [x](<a%00.md>) [x](<A b.md>) ![x](<missing image.png>)\n','a b.md':'# B\n'}).run();
  assert.deepEqual(rules(r), ['URL_SYNTAX','URL_SYNTAX','URL_SYNTAX','URL_ENCODING','PATH_MISSING','PATH_MISSING']);
});
test('resolved formatted and multiline references pass, including collapsed', t => {
  const r = fixture(t, {'a.md':'[**text**][multi\nline] ![*image*][image] [**collapsed**][]\n\n[multi line]: b.md\n[image]: b.md\n[**collapsed**]: b.md\n','b.md':'# B\n'}).run();
  assert.equal(r.errors, 0);
});
test('HTML tokenization accepts actual attributes after quoted delimiters', t => {
  const s = '<DIV title="a > b" ID = "real"></DIV>\n<a title=\'id="fake"\' NAME=legacy></a>\n<span disabled id=bare></span>\n\n[x](#real) [x](#legacy) [x](#bare)\n';
  assert.equal(fixture(t, {'a.md':s}).run().errors, 0);
});
test('HTML tokenization rejects data-id, quoted attribute text and non-anchor names', t => {
  const s = '<div data-id="fake" title=\'id="quoted" <a id="nested">\' aria-id=aria></div>\n<div name="wrong"></div>\n<!-- <a id="comment"></a> -->\n\n[x](#fake) [x](#quoted) [x](#nested) [x](#aria) [x](#wrong) [x](#comment)\n';
  const r = fixture(t, {'a.md':s}).run();
  assert.deepEqual(rules(r), Array(6).fill('FRAGMENT'));
});
test('equivalent ASCII whitespace labels still conflict', t => {
  const r = fixture(t, {'a.md':'[a  b]: b.md\n[A\n B]: c.md\n','b.md':'# B\n','c.md':'# C\n'}).run();
  assert.deepEqual(rules(r), ['REFERENCE_CONFLICT']);
});

test('unresolved full, collapsed, nested and image references remain parser text', t => {
  for (const source of [
    '[x][missing]', '[x][]', '[ordinary prose]', '[**text**][multi\nline]',
    '![*image*][missing]', '[outer [inner]][missing]',
    '[![alt][missing]](https://example.com)',
    '100. > [x][multi\n     > line]\n\n[multi > line]: missing',
  ]) assert.deepEqual(fixture(t, {'a.md':source+'\n'}).run().diagnostics, []);
});
test('unused definition destinations are not independently validated', t => {
  assert.deepEqual(fixture(t, {'a.md':'[unused]: missing.md#bad\n[other]: ftp://host/file\n'}).run().diagnostics, []);
  const r = fixture(t, {'a.md':'[use][ref] ![image][ref]\n\n[ref]: missing.md#bad\n'}).run();
  assert.deepEqual(rules(r), ['PATH_MISSING','PATH_MISSING']);
  assert.deepEqual(r.diagnostics.map(d => [d.line,d.column]), [[1,1],[1,12]]);
  assert.ok(r.diagnostics.every(d => d.message.includes('definition at 3:1')));
});
test('recognized nested reference images and reference anchors are validated', t => {
  const r = fixture(t, {'a.md':'[![alt][image]](https://example.com) [x][target]\n\n[image]: missing.png\n[target]: b.md#absent\n', 'b.md':'# Present\n'}).run();
  assert.deepEqual(rules(r), ['PATH_MISSING','FRAGMENT']);
});
test('only MD009 MD010 MD047 enabled and inline configuration ignored', t => {
  const r = fixture(t, {'a.md':'<!-- markdownlint-disable -->\n#No space\n\n\n### Skipped level\ntext\tX \nlast'}).run();
  assert.deepEqual(rules(r), ['MD010','MD009','MD047']);
  assert.equal(fixture(t, {'a.md':'<!-- markdownlint-enable MD013 MD022 -->\n# Heading\n'+ 'long '.repeat(100)+'word\n\n\n'}).run().errors, 0);
});
test('markdownlint formatting boundaries are used without custom exceptions', t => {
  for (const source of ['one \n', 'one   \n', '`literal   \ncontinued`\n']) {
    assert.deepEqual(rules(fixture(t, {'a.md':source}).run()), ['MD009']);
  }
  for (const source of ['one  \ntwo\n', 'one  \n', '  \n', '# A\n\n\n', '']) {
    assert.equal(fixture(t, {'a.md':source}).run().errors, 0);
  }
  assert.deepEqual(rules(fixture(t, {'a.md':'```\ncode\n```\t\n'}).run()), ['MD009','MD010']);
});
test('archive formatting findings are historical but provenance formatting fails', t => {
  const payload = '# Old\ntext\tX \nlast';
  const policy = {archive:{path:'archive.md',boundary:'<!-- END -->\n\n',sha256:createHash('sha256').update(payload).digest('hex')}};
  const r = fixture(t, {'archive.md':'Notice \n<!-- END -->\n\n'+payload}, policy).run();
  assert.equal(r.errors, 1);
  assert.deepEqual(r.diagnostics.map(d => [d.rule,d.severity]), [['MD009','error'],['MD010','historical'],['MD009','historical'],['MD047','historical']]);
});
test('CLI execution failure exits 2', () => {
  const child = spawnSync(process.execPath, [fileURLToPath(new URL('./check.mjs', import.meta.url)), '--inventory', '/nonexistent-argonaut-inventory'], {encoding:'utf8'});
  assert.equal(child.status, 2);
  assert.match(child.stderr, /Validator failed:/);
});
