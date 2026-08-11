"""Le classeur produit doit etre relisable et arithmetiquement juste."""
from __future__ import annotations

import openpyxl

import extract_releve as ex


def lire(chemin):
    ws = openpyxl.load_workbook(chemin).worksheets[0]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def test_une_ligne_par_operation_entre_les_deux_soldes(depouille, tmp_path):
    soldes, operations = depouille
    sortie = tmp_path / 'releve.xlsx'
    ex.to_excel(soldes, operations, sortie)

    lignes = lire(sortie)
    assert lignes[0] == ex.COLONNES
    assert len(lignes) == 1 + 1 + len(operations) + 1     # entete + 2 soldes
    assert lignes[1][3] == 'SOLDE INITIAL'
    assert lignes[-1][3] == 'SOLDE FINAL'


def test_la_colonne_solde_suit_les_operations(depouille, tmp_path):
    """Le solde courant se cumule ligne a ligne et retombe sur le solde final."""
    soldes, operations = depouille
    sortie = tmp_path / 'releve.xlsx'
    ex.to_excel(soldes, operations, sortie)

    lignes = lire(sortie)
    colonne_solde = ex.COLONNES.index('Solde')
    assert lignes[1][colonne_solde] == soldes[0]['montant']
    assert lignes[-1][colonne_solde] == soldes[-1]['montant']

    courant = soldes[0]['montant']
    for ligne, op in zip(lignes[2:-1], operations):
        courant = round(courant + op.montant, 2)
        assert ligne[colonne_solde] == courant


def test_debit_et_credit_s_excluent(depouille, tmp_path):
    soldes, operations = depouille
    sortie = tmp_path / 'releve.xlsx'
    ex.to_excel(soldes, operations, sortie)

    lignes = lire(sortie)
    debit, credit = ex.COLONNES.index('Debit'), ex.COLONNES.index('Credit')
    for ligne in lignes[2:-1]:
        assert (ligne[debit] is None) != (ligne[credit] is None)
        assert (ligne[debit] or 0) >= 0 and (ligne[credit] or 0) >= 0
