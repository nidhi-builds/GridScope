from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.assets import Pole, TopologyEdge, Transformer
from app.db.models.telemetry import PoleEvidenceState


def network_feature_collection(session: Session) -> dict:
    """The live network: every pole with its current evidence state.

    `pole_evidence_state` already holds exactly what an operator needs to see at
    a glance — which poles are confirmed live, confirmed dark, silent, or have no
    sensor at all. Until now it was only ever read per incident, so the map was
    blank until a ticket was clicked.

    A pole with no row is `uninstrumented`: it has no device, so it reports
    nothing. That is deliberately distinct from `unknown_silent`, which is a pole
    that *should* be reporting and is not. Collapsing the two would be the same
    mistake as treating silence as darkness.
    """
    poles = session.execute(
        select(
            Pole.id, Pole.code, Pole.latitude, Pole.longitude, Pole.transformer_id,
            PoleEvidenceState.evidence_class, PoleEvidenceState.device_health,
        ).outerjoin(PoleEvidenceState, PoleEvidenceState.pole_id == Pole.id)
    ).all()

    coordinates = {row.id: (row.longitude, row.latitude) for row in poles}
    features: list[dict] = [
        {
            "type": "Feature",
            "properties": {
                "asset": "pole",
                "id": str(row.id),
                "code": row.code,
                "transformer_id": str(row.transformer_id),
                "state": row.evidence_class or "uninstrumented",
                "device_health": row.device_health,
            },
            "geometry": {"type": "Point", "coordinates": [row.longitude, row.latitude]},
        }
        for row in poles
    ]

    features += [
        {
            "type": "Feature",
            "properties": {"asset": "transformer", "id": str(row.id), "code": row.code},
            "geometry": {"type": "Point", "coordinates": [row.longitude, row.latitude]},
        }
        for row in session.execute(select(Transformer.id, Transformer.code, Transformer.latitude, Transformer.longitude)).all()
    ]

    # Recorded wiring only. Inferred edges are not drawn as if they were fact —
    # the same reason an inferred topology never emits an exact span.
    for edge in session.execute(select(TopologyEdge.parent_pole_id, TopologyEdge.child_pole_id, TopologyEdge.transformer_id)).all():
        parent, child = coordinates.get(edge.parent_pole_id), coordinates.get(edge.child_pole_id)
        if not parent or not child:
            continue
        features.append({
            "type": "Feature",
            "properties": {"asset": "line", "transformer_id": str(edge.transformer_id)},
            "geometry": {"type": "LineString", "coordinates": [list(parent), list(child)]},
        })

    return {"type": "FeatureCollection", "features": features}
