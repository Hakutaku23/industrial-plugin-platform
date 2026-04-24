from platform_api.services.license_models import LicenseGrantModel, LicensePayloadModel


def test_license_payload_alias_dump():
    payload = LicensePayloadModel(
        license_id='lic-1',
        issuer='issuer',
        customer_name='customer',
        issued_at='2026-01-01T00:00:00+00:00',
        deployment_fingerprint='fp',
        grant=LicenseGrantModel(),
    )
    dumped = payload.model_dump(mode='json', by_alias=True)
    assert dumped['schema'] == 'ipp-license/v1'
    assert 'license_schema' not in dumped


def test_license_grant_defaults():
    grant = LicenseGrantModel()
    assert grant.allow_package_upload is True
    assert grant.allowed_connector_types == []
