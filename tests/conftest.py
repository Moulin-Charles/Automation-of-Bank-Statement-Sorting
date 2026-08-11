"""Fixtures communes : le releve d'exemple et sa verite de reference.

L'extraction d'un PDF coute quelques secondes : elle n'est faite qu'une fois
pour toute la session (scope='session').
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DONNEES = Path(__file__).resolve().parent / 'data'
sys.path.insert(0, str(RACINE))

import extract_releve as ex  # noqa: E402


@pytest.fixture(scope='session')
def chemin_pdf() -> Path:
    return DONNEES / 'releve_exemple.pdf'


@pytest.fixture(scope='session')
def attendu() -> dict:
    """Ce que le PDF d'exemple est cense contenir, declare a la main."""
    return json.loads((DONNEES / 'releve_exemple.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='session')
def lignes(chemin_pdf) -> list:
    """Texte reconstruit a partir des contours vectoriels du PDF."""
    return ex.read_text(chemin_pdf)


@pytest.fixture(scope='session')
def depouille(lignes):
    """-> (soldes, operations) du releve d'exemple."""
    return ex.parse(lignes)
