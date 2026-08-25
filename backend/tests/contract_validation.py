import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

CONTRACTS = Path(__file__).parents[2] / "docs" / "contracts" / "v1"


def load_contracts() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in CONTRACTS.glob("*.schema.json")
    }


CONTRACT_DOCUMENTS = load_contracts()
CONTRACT_REGISTRY = Registry().with_resources(
    (
        contract["$id"],
        Resource.from_contents(contract),
    )
    for contract in CONTRACT_DOCUMENTS.values()
)


def validator_for(filename: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACT_DOCUMENTS[filename],
        registry=CONTRACT_REGISTRY,
        format_checker=FormatChecker(),
    )


def validate_contract(filename: str, payload: object) -> None:
    validator_for(filename).validate(payload)
