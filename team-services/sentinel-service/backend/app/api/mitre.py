from fastapi import APIRouter

from app.utils.mitre_mapper import get_mitre_mapping

router = APIRouter(
    prefix="/mitre",
    tags=["MITRE ATT&CK"],
)


@router.get("/{attack_name}")
def mitre_lookup(attack_name: str):
    return get_mitre_mapping(attack_name)