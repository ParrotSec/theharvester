from types import SimpleNamespace

from theHarvester.discovery import api_endpoints


def test_process_response_extracts_only_string_json_parameter_names(monkeypatch):
    search = api_endpoints.SearchApiEndpoints('example.com')
    response = SimpleNamespace(
        status=200,
        headers={'Content-Type': 'application/json'},
        content=b'{"name": "value"}',
    )

    monkeypatch.setattr(api_endpoints.json, 'loads', lambda _content: {'name': 'value', 1: 'ignored'})

    result = search._process_response('https://example.com/api/v1/users', 'GET', response, 0.1)

    assert result is not None
    assert result.parameters == ['name']
