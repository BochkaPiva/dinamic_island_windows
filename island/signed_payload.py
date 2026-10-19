# SPDX-License-Identifier: GPL-3.0-only
"""Purpose-separated signed envelopes. Trust the exact bytes, never reserialized JSON."""
import base64
import json


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError('Duplicate signed JSON key')
        result[key]=value
    return result


def decode_json(raw):
    if len(raw)>65536: raise ValueError('Signed document too large')
    return json.loads(raw,object_pairs_hook=_object,
                      parse_constant=lambda value:(_ for _ in ()).throw(ValueError('Non-finite number')))


def verify_envelope(envelope,keys,purpose):
    # Do not load the Rust/OpenSSL runtime just to display an unlicensed/preview
    # desktop. Cryptography is needed only when there is a document to verify.
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    try:
        if isinstance(envelope,(bytes,str)): envelope=decode_json(envelope)
        if not isinstance(envelope,dict) or set(envelope)!={'key_id','payload','signature'}:
            raise ValueError('Invalid signed envelope')
        public=keys[envelope['key_id']]
        raw=base64.b64decode(envelope['payload'],validate=True)
        signature=base64.b64decode(envelope['signature'],validate=True)
        key=Ed25519PublicKey.from_public_bytes(base64.b64decode(public,validate=True))
        key.verify(signature,purpose.encode('ascii')+b'\0'+raw)
        value=decode_json(raw)
        if not isinstance(value,dict): raise ValueError('Invalid signed document')
        return value
    except (InvalidSignature,KeyError,TypeError,UnicodeError) as exc:
        raise ValueError('Untrusted signed document') from exc
