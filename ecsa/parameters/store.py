"""ParameterStore — the only way engines obtain operational values.

Resolution order for a key at an as-of date:
  1. governorate-specific row with the latest effective_from <= as_of
  2. global row (governorate IS NULL) with the latest effective_from <= as_of
A missing key raises MissingParameterError; engines never fall back to
hard-coded numbers (CLAUDE.md rule 1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from importlib import resources
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ecsa.db.models import Parameter


class MissingParameterError(KeyError):
    pass


@dataclass
class ParameterSet:
    """Immutable-ish snapshot of resolved parameters, passed to engines."""
    values: dict[str, str] = field(default_factory=dict)
    governorate: str | None = None
    as_of: date | None = None

    def get(self, key: str) -> str:
        try:
            return self.values[key]
        except KeyError as e:
            raise MissingParameterError(f"parameter '{key}' is not defined (governorate={self.governorate})") from e

    def float(self, key: str) -> float:
        v = self.get(key).strip().rstrip("%")
        f = float(v)
        return f / 100.0 if self.get(key).strip().endswith("%") else f

    def int(self, key: str) -> int:
        return int(round(self.float(key)))

    def has(self, key: str) -> bool:
        return key in self.values

    def with_overrides(self, overrides: dict[str, Any] | None) -> "ParameterSet":
        if not overrides:
            return self
        merged = dict(self.values)
        merged.update({k: str(v) for k, v in overrides.items()})
        return ParameterSet(merged, self.governorate, self.as_of)

    def snapshot(self) -> dict[str, str]:
        return dict(self.values)

    @classmethod
    def from_dict(cls, d: dict[str, Any], governorate: str | None = None) -> "ParameterSet":
        return cls({k: str(v) for k, v in d.items()}, governorate)


class ParameterStore:
    def __init__(self, session: Session):
        self.s = session

    def resolve(self, governorate: str | None = None, as_of: date | None = None) -> ParameterSet:
        as_of = as_of or date.today()
        rows = self.s.execute(
            select(Parameter)
            .where(Parameter.effective_from <= as_of)
            .where((Parameter.governorate.is_(None)) | (Parameter.governorate == governorate))
            .order_by(Parameter.param_key, Parameter.effective_from)
        ).scalars().all()
        resolved: dict[str, str] = {}
        specific: set[str] = set()
        for r in rows:
            if r.governorate is None:
                if r.param_key not in specific:
                    resolved[r.param_key] = r.param_value
            else:
                resolved[r.param_key] = r.param_value
                specific.add(r.param_key)
        return ParameterSet(resolved, governorate, as_of)

    def set(self, key: str, value: Any, *, governorate: str | None = None, unit: str | None = None,
            effective_from: date | None = None, description: str | None = None) -> Parameter:
        effective_from = effective_from or date.today()
        existing = self.s.execute(
            select(Parameter).where(Parameter.param_key == key, Parameter.governorate.is_(governorate) if governorate is None else Parameter.governorate == governorate,
                                    Parameter.effective_from == effective_from)
        ).scalar_one_or_none()
        if existing:
            existing.param_value = str(value)
            if unit is not None:
                existing.unit = unit
            if description is not None:
                existing.description = description
            return existing
        p = Parameter(param_key=key, param_value=str(value), unit=unit, governorate=governorate,
                      effective_from=effective_from, description=description)
        self.s.add(p)
        self.s.flush()
        return p

    def list_all(self, governorate: str | None = None) -> list[Parameter]:
        q = select(Parameter).order_by(Parameter.param_key, Parameter.governorate, Parameter.effective_from)
        if governorate is not None:
            q = q.where((Parameter.governorate.is_(None)) | (Parameter.governorate == governorate))
        return list(self.s.execute(q).scalars().all())


def load_default_definitions() -> list[dict]:
    with resources.files("ecsa.parameters").joinpath("defaults.json").open("r", encoding="utf-8") as f:
        return json.load(f)


def seed_default_parameters(session: Session, definitions: Iterable[dict] | None = None,
                            effective_from: date = date(2000, 1, 1)) -> int:
    """Insert global defaults for any key that has no global row yet. Returns count inserted."""
    definitions = list(definitions) if definitions is not None else load_default_definitions()
    existing = set(session.execute(select(Parameter.param_key).where(Parameter.governorate.is_(None))).scalars().all())
    n = 0
    for d in definitions:
        if d["param_key"] in existing:
            continue
        session.add(Parameter(param_key=d["param_key"], param_value=str(d["param_value"]), unit=d.get("unit"),
                              governorate=None, effective_from=effective_from, description=d.get("description")))
        n += 1
    session.flush()
    return n
