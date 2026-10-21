import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {unified} from 'unified';
import remarkParse from 'remark-parse';
import remarkGfm from 'remark-gfm';
import Slugger from 'github-slugger';
import {lint} from 'markdownlint/sync';

const parser = unified().use(remarkParse).use(remarkGfm);
const md = p => /\.(md|markdown)$/i.test(p);
const hash = b => createHash('sha256').update(b).digest('hex');
const cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
const walk = (n, fn) => { fn(n); for (const c of n.children || []) walk(c, fn); };
const rendered = n => n.type === 'html' ? '' : n.value ?? n.alt ?? (n.children || []).map(rendered).join('');
export function inventory(root) {
  return execFileSync('git', ['-C', root, 'ls-files', '-z'], {maxBuffer: 32 * 1024 * 1024}).toString('utf8').split('\0').filter(Boolean);
}
export function annotation(d) {
  const escape = s => String(s).replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
  const prop = s => escape(s).replaceAll(':', '%3A').replaceAll(',', '%2C');
  return `::${d.severity === 'error' ? 'error' : 'warning'} file=${prop(d.path)},line=${d.line},col=${d.column},title=${prop(d.rule)}::${escape(d.message + (d.destination ? '; ' + d.destination : ''))}`;
}
export function validate(root, files, policy = {}) {
  root = fs.realpathSync(root);
  const tracked = new Set(files), dirs = new Set(['.']);
  for (const f of files) {
    if (path.posix.isAbsolute(f) || f.split('/').includes('..') || f.includes('\\')) throw Error('Unsafe inventory path');
    for (let d = path.posix.dirname(f); d !== '.'; d = path.posix.dirname(d)) dirs.add(d);
  }
  const diagnostics = [], documents = new Map();
  const add = (p, pos, rule, message, destination = '', severity = 'error') => {
    const offset = pos?.offset ?? 0;
    if (documents.get(p)?.archiveStart <= offset && !rule.startsWith('ARCHIVE_')) severity = 'historical';
    diagnostics.push({path:p, line:pos?.line ?? 1, column:pos?.column ?? 1, rule, severity, message, destination});
  };
  // Reject all symlink traversal, including tracked links to otherwise safe targets.
  const safe = p => {
    let current = root;
    for (const part of p.split('/')) {
      current = path.join(current, part);
      if (fs.lstatSync(current).isSymbolicLink()) return false;
    }
    return true;
  };
  for (const p of [...tracked].filter(md).sort(cmp)) {
    try {
      if (!safe(p)) { add(p, null, 'PATH_SYMLINK', 'Markdown source traverses a symlink'); continue; }
      const bytes = fs.readFileSync(path.join(root, p));
      let source;
      try { source = new TextDecoder('utf-8', {fatal:true, ignoreBOM:true}).decode(bytes); }
      catch { add(p, null, 'UTF8', 'Invalid UTF-8'); continue; }
      const tree = parser.parse(source), nodes = [];
      walk(tree, n => nodes.push(n));
      const doc = {source, tree, nodes, anchors:new Set(), archiveStart:Infinity};
      documents.set(p, doc);
      if (policy.archive?.path === p) {
        const boundary = policy.archive.boundary;
        const at = source.indexOf(boundary);
        if (at < 0 || source.indexOf(boundary, at + boundary.length) >= 0) add(p, null, 'ARCHIVE_BOUNDARY', 'Archive boundary missing or duplicated');
        else {
          doc.archiveStart = at + boundary.length;
          if (hash(Buffer.from(source.slice(doc.archiveStart))) !== policy.archive.sha256) add(p, null, 'ARCHIVE_HASH', 'Archive payload differs from pinned SHA-256');
        }
      }
      const slugger = new Slugger();
      for (const n of nodes) {
        if (n.type === 'heading') doc.anchors.add(slugger.slug(rendered(n)));
        if (n.type === 'html') {
          // Consume whole tags and attribute values so data-id and quoted text
          // cannot masquerade as attributes. Comments are consumed as tokens.
          const tags = /<!--[\s\S]*?(?:-->|$)|<([a-z][\w:-]*)((?:[^"'<>]|"[^"]*"|'[^']*')*)>/gi;
          for (const tag of n.value.matchAll(tags)) {
            if (!tag[1]) continue;
            const attrs = /[ \t\r\n]+([^\s"'<>/=]+)(?:[ \t\r\n]*=[ \t\r\n]*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/gy;
            let a;
            while ((a = attrs.exec(tag[2]))) {
              const name = a[1].toLowerCase();
              if (name !== 'id' && !(name === 'name' && tag[1].toLowerCase() === 'a')) continue;
              const id = a[2] ?? a[3] ?? a[4];
              if (id === undefined) continue;
              if (doc.anchors.has(id)) add(p, n.position.start, 'ANCHOR_DUPLICATE', 'Duplicate explicit anchor', id);
              doc.anchors.add(id);
            }
          }
        }
      }
    } catch (e) { add(p, null, 'READ', e.code || e.message); }
  }
  if (policy.archive && !documents.has(policy.archive.path)) add(policy.archive.path, null, 'ARCHIVE_MISSING', 'Required archive is absent');
  for (const [p, doc] of documents) {
    const {source, nodes} = doc;
    const position = offset => {
      const before = source.slice(0, offset), line = before.split('\n').length;
      return {offset, line, column:offset - before.lastIndexOf('\n')};
    };
    if (source.startsWith('\uFEFF')) add(p, null, 'BOM', 'UTF-8 BOM is forbidden');
    for (const m of source.matchAll(/\r/g)) add(p, position(m.index), 'LF', 'Use LF line endings');
    const lineOffsets = [0];
    for (let i = 0; i < source.length; i++) if (source[i] === '\n') lineOffsets.push(i + 1);
    const findings = lint({
      strings: {document: source},
      config: {default: false, MD009: {br_spaces: 2, strict: false}, MD010: {code_blocks: false}, MD047: true},
      noInlineConfig: true,
    }).document;
    for (const finding of findings) {
      const column = finding.errorRange?.[0] ?? 1;
      add(p, {line: finding.lineNumber, column, offset: lineOffsets[finding.lineNumber - 1] + column - 1},
        finding.ruleNames[0], finding.ruleDescription + (finding.errorDetail ? `; ${finding.errorDetail}` : ''));
    }
    const definitions = new Map();
    for (const n of nodes.filter(n => n.type === 'definition')) {
      const key = n.identifier, old = definitions.get(key);
      if (old && (old.url !== n.url || old.title !== n.title)) add(p, n.position.start, 'REFERENCE_CONFLICT', `Conflicting definition; first at ${old.position.start.line}:${old.position.start.column}`, n.url);
      else definitions.set(key, n);
    }
    const check = (url, pos, definition) => {
      const issue = (rule, message) => add(p, pos, rule, message + (definition ? `; definition at ${definition.position.start.line}:${definition.position.start.column}` : ''), url);
      if (/[\x00-\x1f\x7f\\]/.test(url) || /%(?![\da-f]{2})/i.test(url)) { issue('URL_SYNTAX', 'Control, backslash or malformed percent escape'); return; }
      let decoded;
      try { decoded = decodeURIComponent(url); } catch { issue('URL_ENCODING', 'Invalid UTF-8 percent encoding'); return; }
      if (/[\x00-\x1f\x7f\\]/.test(decoded)) { issue('URL_ENCODING', 'Encoded control or backslash'); return; }
      if (/^[a-z][a-z\d+.-]*:/i.test(url) || url.startsWith('//')) {
        try {
          const u = new URL(url.startsWith('//') ? 'https:' + url : url);
          if (['http:', 'https:'].includes(u.protocol)) {
            if (!u.hostname || !/^(https?:)?\/\//i.test(url)) throw Error();
          } else if (u.protocol === 'mailto:') {
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(decodeURIComponent(u.pathname))) throw Error();
          } else { issue('URL_SCHEME', 'Unsupported external scheme'); }
        } catch { issue('URL_SYNTAX', 'Malformed external destination'); }
        return;
      }
      const [beforeHash, ...fragments] = url.split('#');
      const rawPath = beforeHash.split('?')[0];
      const local = decodeURIComponent(rawPath);
      const target = local ? path.posix.normalize(local.startsWith('/') ? local.slice(1) : path.posix.join(path.posix.dirname(p), local)).replace(/\/$/, '') || '.' : p;
      if (target === '..' || target.startsWith('../') || path.posix.isAbsolute(target)) { issue('PATH_ESCAPE', 'Destination escapes repository'); return; }
      if (!tracked.has(target) && !dirs.has(target)) { issue('PATH_MISSING', 'Destination is not tracked with exact case'); return; }
      try { if (!safe(target)) { issue('PATH_SYMLINK', 'Destination traverses a symlink'); return; } }
      catch { issue('PATH_MISSING', 'Tracked destination absent from source'); return; }
      if (fragments.length && fragments.join('#')) {
        const fragment = decodeURIComponent(fragments.join('#'));
        if (md(target) && !documents.get(target)?.anchors.has(fragment)) issue('FRAGMENT', 'Heading or explicit anchor does not exist');
      }
    };
    for (const n of nodes) {
      if (['link', 'image'].includes(n.type)) check(n.url, n.position.start);
      if (['linkReference', 'imageReference'].includes(n.type)) {
        const d = definitions.get(n.identifier);
        if (d) check(d.url, n.position.start, d);
      }
    }

  }
  const used = new Set();
  for (const d of diagnostics) {
    for (const [i, e] of (policy.exceptions || []).entries()) {
      if (!d.rule.startsWith('ARCHIVE_') && e.reason && e.path === d.path && e.rule === d.rule && e.destination === d.destination && e.line === d.line) {
        d.severity = 'exception'; d.reason = e.reason; used.add(i);
      }
    }
  }
  for (const [i, e] of (policy.exceptions || []).entries()) if (!used.has(i)) add(e.path || 'policy.json', null, 'EXCEPTION_UNUSED', 'Unused or invalid exception');
  diagnostics.sort((a,b) => cmp(a.path,b.path) || a.line-b.line || a.column-b.column || cmp(a.rule,b.rule) || cmp(a.destination,b.destination));
  return {documents:[...documents.keys()], diagnostics, errors:diagnostics.filter(d => d.severity === 'error').length};
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const args = process.argv.slice(2), option = (name, fallback) => args.includes(name) ? args[args.indexOf(name)+1] : fallback;
    const root = path.resolve(option('--root', '.'));
    const list = option('--inventory');
    const files = list ? fs.readFileSync(list, 'utf8').split('\0').filter(Boolean) : inventory(root);
    const policy = JSON.parse(fs.readFileSync(new URL('./policy.json', import.meta.url)));
    const result = validate(root, files, policy);
    const json = option('--json');
    if (json) fs.writeFileSync(json, JSON.stringify(result, null, 2) + '\n');
    for (const d of result.diagnostics) {
      console.log(`${JSON.stringify(d.path)}:${d.line}:${d.column}: ${d.rule}: ${d.message}; ${JSON.stringify(d.destination)} [${d.severity}]`);
      if (args.includes('--github')) console.log(annotation(d));
    }
    console.log(`${result.documents.length} Markdown documents; ${result.errors} errors`);
    process.exitCode = result.errors ? 1 : 0;
  } catch (e) { console.error(`Validator failed: ${e.message}`); process.exitCode = 2; }
}
