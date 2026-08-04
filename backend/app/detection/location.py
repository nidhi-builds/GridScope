from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.detection.localization import BoundaryResult, midpoint_of_path


@dataclass(frozen=True)
class LocationResult:
    latitude: float | None
    longitude: float | None
    pin_code: str | None
    pin_source: str


def resolve_location(boundary: BoundaryResult, assets: Any) -> LocationResult:
    """Resolve navigation and PIN without external geocoding."""
    if boundary.kind == "dt":
        asset = _asset(assets, boundary.transformer_id)
        return _asset_location(asset, boundary, assets)
    if boundary.kind == "feeder":
        members = [item for item in _assets(assets) if _value(item, "feeder_id") == boundary.feeder_id]
        if members:
            point = (sum(_point(item)[0] for item in members) / len(members), sum(_point(item)[1] for item in members) / len(members))
            return _pin_location(point, boundary, assets)
    asset = _asset(assets, boundary.downstream_pole_id)
    point = boundary.navigation_point or midpoint_of_path(boundary.geometry) or _point(asset)
    pin = _value(asset, "pin_code") if asset else None
    if pin:
        return LocationResult(*(point or (None, None)), pin, "registry")
    candidates = [item for item in _assets(assets) if _value(item, "transformer_id") == boundary.transformer_id and _value(item, "pin_code")]
    if candidates:
        nearest = min(candidates, key=lambda item: _distance(_point(asset) or point, _point(item)))
        return LocationResult(*(point or _point(nearest) or (None, None)), _value(nearest, "pin_code"), "nearest-registry")
    lookup = _value(assets, "offline_pin_lookup", {})
    pin = lookup.get(boundary.transformer_id) if isinstance(lookup, Mapping) else None
    return LocationResult(*(point or (None, None)), pin, "offline-inferred")


def _asset_location(asset: Any, boundary: BoundaryResult, assets: Any) -> LocationResult:
    return _pin_location(_point(asset), boundary, assets)


def _pin_location(point: tuple[float, float] | None, boundary: BoundaryResult, assets: Any) -> LocationResult:
    transformer_ids = {boundary.transformer_id} if boundary.transformer_id else {
        _value(item, "id") for item in _assets(assets) if _value(item, "feeder_id") == boundary.feeder_id
    }
    candidates = [item for item in _assets(assets) if _value(item, "transformer_id") in transformer_ids and _value(item, "pin_code")]
    if candidates:
        nearest = min(candidates, key=lambda item: _distance(point, _point(item)))
        return LocationResult(*(point or _point(nearest) or (None, None)), _value(nearest, "pin_code"), "nearest-registry")
    lookup = _value(assets, "offline_pin_lookup", {})
    pin = lookup.get(boundary.transformer_id or boundary.feeder_id) if isinstance(lookup, Mapping) else None
    return LocationResult(*(point or (None, None)), pin, "offline-inferred")


def _assets(assets: Any) -> list[Any]:
    return [value for value in assets.values() if _value(value, "id") is not None] if isinstance(assets, Mapping) else list(assets)


def _asset(assets: Any, asset_id: Any) -> Any:
    return assets.get(asset_id) if isinstance(assets, Mapping) else next((item for item in assets if _value(item, "id") == asset_id), None)


def _point(asset: Any) -> tuple[float, float] | None:
    latitude, longitude = _value(asset, "latitude"), _value(asset, "longitude")
    return (latitude, longitude) if latitude is not None and longitude is not None else None


def _distance(first: tuple[float, float] | None, second: tuple[float, float] | None) -> float:
    if first is None or second is None:
        return float("inf")
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2


def _value(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)
