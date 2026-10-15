# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded one-item publication contract. Data is never execution authority."""
from dataclasses import dataclass
import hashlib
import json
import unicodedata
from uuid import UUID, uuid5
from .api import BrowserError
from .managed_library import parse_manifest

ROOT = '/USB0/ARGONAUT_LIBRARY'
LIBRARY = 'a3b6d459-a989-4224-a372-0a995628f7ce'
TRANSACTION = 'e2542704-23f4-449f-8b45-8b9ca6a9344b'
DEVICE = 'id:25EA78'
DIRECTORY = ROOT + '/argonaut-import-' + TRANSACTION
PAYLOAD = '78d99754a49326515d55f69fc7ac55e1984e0bb3b38b8a46466621e0add44d51'
OLD_HASH = '485cd2d9f5310a200e43ad639c549faf9df60542fabc56c1cb093636e7b9aa8e'
RECORD_HASH = 'b4c6b3c712d120790954048eee41fc75552dc55b21bbd74c234de4b127e1fd2f'
SIZE = 174848
CREATED = '2026-10-11T23:08:58.115082+00:00'
FINAL = ROOT + '/games/C64Robots v1.3.d64'

class PublicationError(BrowserError):
    code = 'managed-publication-stopped'
    retryable = False


def require(condition, message):
    if not condition: raise PublicationError(message)


def digest(data): return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')


def confirmed_title(value):
    require(type(value) is str, 'Explicit title required.')
    value = unicodedata.normalize('NFC', value.strip())
    require(1 <= len(value) <= 512 and all(unicodedata.category(c) != 'Cc' for c in value),
            'Title exceeds bounds or contains controls.')
    return value


def game_id():
    return str(uuid5(UUID(LIBRARY), 'argonaut-managed-game-v1:' + TRANSACTION + ':item-0001:' + PAYLOAD))


@dataclass(frozen=True)
class PublicationPlan:
    attempt: str
    title: str
    old_manifest: bytes
    record: bytes
    manifest: bytes
    metadata: bytes
    history_digest: str
    session_id: str = ""
    adapter_owner: str = ""

    @property
    def source(self): return DIRECTORY + '/item-0001.d64'
    @property
    def metadata_pending(self): return DIRECTORY + '/metadata.pending-' + self.attempt + '.json'
    @property
    def metadata_final(self): return ROOT + '/metadata/' + game_id() + '.json'
    @property
    def pending(self): return ROOT + '/manifest.pending-' + self.attempt
    @property
    def backup(self): return ROOT + '/manifest.backup-' + self.attempt
    @property
    def mutations(self):
        return (('STOR', '', self.metadata_pending), ('STOR', '', self.pending),
                ('rename', self.source, FINAL), ('rename', self.metadata_pending, self.metadata_final),
                ('rename', ROOT + '/manifest.json', self.backup),
                ('rename', self.pending, ROOT + '/manifest.json'))

    def proof(self):
        return dict(attempt=self.attempt, title=self.title, library=LIBRARY, device=DEVICE,
            session_id=self.session_id,adapter_owner=self.adapter_owner,
            transaction=TRANSACTION, game_id=game_id(), payload_sha256=PAYLOAD, size=SIZE,
            old_manifest_hex=self.old_manifest.hex(), record_hex=self.record.hex(),
            manifest_hex=self.manifest.hex(), metadata_hex=self.metadata.hex(),
            history_digest=self.history_digest, mutations=self.mutations,
            schema_version=1, execution_policy_version=1, resource_policy_version=1,
            staging_versions=[3,5,4,2], cancellation='pa51b-dispatch-boundary')

    @property
    def sha256(self): return digest(canonical(self.proof()))


def make_plan(attempt, title, old_manifest, record, history_digest):
    require(str(UUID(attempt)) == attempt and UUID(attempt).version == 4, 'Fresh canonical UUID4 required.')
    title = confirmed_title(title)
    require(type(old_manifest) is bytes and len(old_manifest) == 181 and digest(old_manifest) == OLD_HASH,
            'Historical manifest mismatch.')
    library = parse_manifest(old_manifest, DEVICE, ROOT)
    require(library.identity.library_id == LIBRARY and library.created_at == CREATED and
            library.revision == 0 and not library.games, 'Revision-zero empty library required.')
    require(type(record) is bytes and len(record) == 777 and digest(record) == RECORD_HASH,
            'Historical format-3 record mismatch.')
    doc = json.loads(record)
    require(canonical(doc) == record and (doc['format_version'],doc['journal_schema_version'],
            doc['execution_policy_version'],doc['policy_version']) == (3,5,4,2), 'Record versions changed.')
    require(doc['transaction_id'] == TRANSACTION and doc['library'] == library.identity.preference() and
            doc['directory'] == DIRECTORY.rsplit('/',1)[1] and
            doc['manifest'] == dict(revision=0,sha256=OLD_HASH) and
            doc['items'] == [dict(final_path=FINAL[len(ROOT)+1:], staged_path=DIRECTORY[len(ROOT)+1:]+'/item-0001.d64',
                                  format='D64',size=SIZE,sha256=PAYLOAD)], 'Record declarations changed.')
    require(type(history_digest) is str and len(history_digest)==64 and all(c in '0123456789abcdef' for c in history_digest),
            'Validated historical proof required.')
    entry = dict(id=game_id(),path=FINAL[len(ROOT)+1:],title=title,format='D64',size=SIZE,
                 sha256=PAYLOAD,metadata_path='metadata/'+game_id()+'.json')
    manifest = canonical(dict(schema_version=1,application='argonaut',library_id=LIBRARY,
                             created_at=CREATED,revision=1,games=[entry]))
    metadata = canonical(dict(schema_version=1,application='argonaut',game_id=game_id(),library_id=LIBRARY,
        title=title,title_source='operator-confirmed',format='D64',size=SIZE,sha256=PAYLOAD,
        staging_transaction_id=TRANSACTION,staged_item='item-0001.d64'))
    require(max(len(manifest),len(metadata)) <= 4096, 'Control file exceeds publication allowance.')
    parse_manifest(manifest, DEVICE, ROOT)
    return PublicationPlan(attempt,title,old_manifest,record,manifest,metadata,history_digest)
