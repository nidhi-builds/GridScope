from dataclasses import replace
from math import cos, hypot, sin
from random import Random
from uuid import UUID, uuid5

from app.domain.types import (
    BranchPolyline,
    DeviceAsset,
    FeederAsset,
    GeneratedNetwork,
    PoleAsset,
    SubstationAsset,
    TransformerAsset,
)

_NAMESPACE = UUID("4cc8505a-ff92-4f18-bfdd-f742ecaad280")
_TRANSFORMER_COUNT = 60


def _id(seed: int, kind: str, index: int) -> UUID:
    return uuid5(_NAMESPACE, f"{seed}:{kind}:{index}")


def _pole_counts(rng: Random, target: int) -> list[int]:
    minimum = _TRANSFORMER_COUNT * 9
    maximum = _TRANSFORMER_COUNT * 240
    if not minimum <= target <= maximum:
        raise ValueError(f"pole_target must be between {minimum} and {maximum}")

    base, remainder = divmod(target, _TRANSFORMER_COUNT)
    counts = [base + (index < remainder) for index in range(_TRANSFORMER_COUNT)]
    order = list(range(_TRANSFORMER_COUNT))
    rng.shuffle(order)
    smallest, largest, *donors = order
    if target <= 9 + (_TRANSFORMER_COUNT - 1) * 240:
        surplus = counts[smallest] - 9
        counts[smallest] = 9
        for index in (largest, *donors):
            moved = min(240 - counts[index], surplus)
            counts[index] += moved
            surplus -= moved
            if surplus == 0:
                break

    if target >= 240 + (_TRANSFORMER_COUNT - 1) * 9:
        needed = 240 - counts[largest]
        for index in donors:
            taken = min(counts[index] - 9, needed)
            counts[index] -= taken
            counts[largest] += taken
            needed -= taken
            if needed == 0:
                break
    return counts


def _point_on_line(
    points: tuple[tuple[float, float], ...], fraction: float
) -> tuple[float, float]:
    lengths = [hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:])]
    distance = sum(lengths) * fraction
    for (start, end), length in zip(zip(points, points[1:]), lengths):
        if distance <= length:
            ratio = distance / length if length else 0.0
            return (
                start[0] + (end[0] - start[0]) * ratio,
                start[1] + (end[1] - start[1]) * ratio,
            )
        distance -= length
    return points[-1]


def generate_network(seed: int, pole_target: int = 4200) -> GeneratedNetwork:
    rng = Random(seed)
    substations = tuple(
        SubstationAsset(
            id=_id(seed, "substation", index),
            code=f"SS-{index + 1:02d}",
            latitude=12.91 + (index // 2) * 0.13,
            longitude=77.50 + (index % 2) * 0.16,
        )
        for index in range(4)
    )
    feeders = tuple(
        FeederAsset(
            id=_id(seed, "feeder", index),
            substation_id=substations[index // 3].id,
            code=f"FDR-{index + 1:02d}",
        )
        for index in range(12)
    )
    transformers = tuple(
        TransformerAsset(
            id=_id(seed, "transformer", index),
            feeder_id=feeders[index // 5].id,
            code=f"DT-{index + 1:03d}",
            latitude=12.90 + (index // 10) * 0.025 + rng.uniform(-0.004, 0.004),
            longitude=77.49 + (index % 10) * 0.018 + rng.uniform(-0.004, 0.004),
        )
        for index in range(_TRANSFORMER_COUNT)
    )

    hidden_poles: list[PoleAsset] = []
    polylines: list[BranchPolyline] = []
    pole_index = 0
    for transformer, count in zip(transformers, _pole_counts(rng, pole_target)):
        branch_count = rng.randint(1, 5)
        branch_sizes = [count // branch_count] * branch_count
        for index in range(count % branch_count):
            branch_sizes[index] += 1

        for branch_index, branch_size in enumerate(branch_sizes, start=1):
            angle = rng.uniform(0.0, 6.283185307179586)
            length = rng.uniform(0.004, 0.018)
            turn = rng.uniform(-0.7, 0.7)
            start = (transformer.latitude, transformer.longitude)
            middle = (
                start[0] + 0.52 * length * cos(angle),
                start[1] + 0.52 * length * sin(angle),
            )
            end = (
                middle[0] + 0.48 * length * cos(angle + turn),
                middle[1] + 0.48 * length * sin(angle + turn),
            )
            line = BranchPolyline(transformer.id, branch_index, (start, middle, end))
            polylines.append(line)
            parent_id = transformer.id
            for sequence in range(1, branch_size + 1):
                latitude, longitude = _point_on_line(line.points, sequence / branch_size)
                pole_id = _id(seed, "pole", pole_index)
                hidden_poles.append(
                    PoleAsset(
                        id=pole_id,
                        transformer_id=transformer.id,
                        code=f"PL-{pole_index + 1:05d}",
                        latitude=round(latitude, 7),
                        longitude=round(longitude, 7),
                        pin_code=str(560001 + pole_index % 999),
                        parent_id=parent_id,
                        branch_index=branch_index,
                        seq_on_line=sequence,
                    )
                )
                parent_id = pole_id
                pole_index += 1

    transformer_indexes = list(range(len(transformers)))
    rng.shuffle(transformer_indexes)
    masked_transformers = {
        transformers[index].id for index in transformer_indexes[: round(len(transformers) * 0.60)]
    }
    pole_indexes = list(range(len(hidden_poles)))
    rng.shuffle(pole_indexes)
    missing_pin_indexes = set(pole_indexes[: round(len(hidden_poles) * 0.03)])
    exported_poles = tuple(
        replace(
            pole,
            parent_id=None if pole.transformer_id in masked_transformers else pole.parent_id,
            seq_on_line=None if pole.transformer_id in masked_transformers else pole.seq_on_line,
            pin_code=None if index in missing_pin_indexes else pole.pin_code,
        )
        for index, pole in enumerate(hidden_poles)
    )

    device_indexes = list(range(len(hidden_poles)))
    rng.shuffle(device_indexes)
    device_indexes = device_indexes[: round(len(hidden_poles) * 0.91)]
    firmware_indexes = set(rng.sample(device_indexes, round(len(device_indexes) * 0.08)))
    offline_indexes = set(rng.sample(device_indexes, round(len(device_indexes) * 0.04)))
    devices = []
    for index in device_indexes:
        is_online = index not in offline_indexes
        interval = rng.randint(855, 945)
        devices.append(
            DeviceAsset(
                id=_id(seed, "device", index),
                pole_id=hidden_poles[index].id,
                serial_number=f"GS-{index + 1:06d}",
                firmware=f"1.2.{rng.randint(0, 9)}" if index in firmware_indexes else f"1.{rng.randint(3, 4)}.{rng.randint(0, 9)}",
                battery_pct=round(rng.uniform(35.0, 100.0), 1),
                rssi_dbm=round(rng.uniform(-105.0, -55.0), 1),
                is_online=is_online,
                heartbeat_interval_seconds=interval,
                next_heartbeat_offset_seconds=rng.randrange(interval) if is_online else None,
            )
        )

    return GeneratedNetwork(
        substations=substations,
        feeders=feeders,
        transformers=transformers,
        hidden_poles=tuple(hidden_poles),
        exported_poles=exported_poles,
        devices=tuple(devices),
        branch_polylines=tuple(polylines),
        masked_transformer_ids=tuple(sorted(masked_transformers, key=str)),
    )
