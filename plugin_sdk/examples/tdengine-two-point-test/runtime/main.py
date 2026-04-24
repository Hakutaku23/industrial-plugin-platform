from __future__ import annotations

from typing import Any


def _to_rows(payload: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    if not isinstance(payload, dict) or payload.get('__ipp_type') != 'dataframe':
        raise ValueError('history_df must be an IPP dataframe payload')
    columns = [str(item) for item in payload.get('columns', [])]
    data = payload.get('data', [])
    if not isinstance(data, list):
        raise ValueError('history_df.data must be a list')
    return columns, data


def _column_values(columns: list[str], data: list[list[Any]], name: str) -> list[float]:
    try:
        index = columns.index(name)
    except ValueError as exc:
        raise ValueError(f'missing required column: {name}') from exc
    values: list[float] = []
    for row in data:
        if not isinstance(row, list) or index >= len(row):
            continue
        value = row[index]
        if value is None:
            continue
        values.append(float(value))
    if not values:
        raise ValueError(f'column has no numeric values: {name}')
    return values


def run(payload: dict[str, Any]) -> dict[str, Any]:
    inputs = payload.get('inputs', {})
    history_df = inputs.get('history_df')
    columns, data = _to_rows(history_df)
    ao_001 = _column_values(columns, data, 'DCS_AO_001')
    ao_002 = _column_values(columns, data, 'DCS_AO_002')
    latest_delta = ao_001[-1] - ao_002[-1]
    return {
        'status': 'success',
        'outputs': {
            'ao_001_mean': sum(ao_001) / len(ao_001),
            'ao_002_mean': sum(ao_002) / len(ao_002),
            'latest_delta': latest_delta,
            'row_count': len(data),
        },
        'logs': [
            f'columns={columns}',
            f'rows={len(data)}',
            f'latest_delta={latest_delta:.6f}',
        ],
        'metrics': {
            'input_rows': len(data),
            'ao_001_points': len(ao_001),
            'ao_002_points': len(ao_002),
        },
    }
