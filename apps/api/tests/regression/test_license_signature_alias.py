from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from platform_api.services.license_crypto import sign_payload, verify_payload_signature
from platform_api.services.license_models import LicenseEnvelopeModel


def test_license_signature_verification_uses_alias_field_names():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode('utf-8')
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode('utf-8')

    payload = {
        'schema': 'ipp-license/v1',
        'license_id': 'lic-test-001',
        'issuer': 'Test Issuer',
        'customer_name': 'Test Customer',
        'issued_at': '2026-04-23T00:00:00+00:00',
        'deployment_fingerprint': 'fp-test',
        'grant': {
            'mode': 'perpetual',
            'not_before': None,
            'not_after': None,
            'allow_manual_run': True,
            'allow_schedule': True,
            'allow_real_writeback': True,
            'max_instances': 10,
            'max_packages': 10,
            'max_data_sources': 10,
            'max_concurrent_runs': 2,
        },
        'metadata': {},
    }
    signature = sign_payload(payload, private_pem)
    envelope = LicenseEnvelopeModel.model_validate({
        'payload': payload,
        'key_id': 'issuer-main-2026',
        'algorithm': 'Ed25519',
        'signature': signature,
    })

    dumped = envelope.payload.model_dump(mode='json', by_alias=True, exclude_none=False)
    assert 'schema' in dumped
    assert 'license_schema' not in dumped
    verify_payload_signature(dumped, signature, public_pem)
