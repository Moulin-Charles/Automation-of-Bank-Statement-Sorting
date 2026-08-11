"""Ce que l'extraction doit garantir sur le releve d'exemple.

Les tests portent sur des proprietes verifiables de l'exterieur -- le solde se
reconstitue, aucune operation ne manque, les libelles sont ceux du releve --
et non sur la maniere dont le decodage s'y prend.
"""
from __future__ import annotations

from datetime import date

import pytest

import extract_releve as ex


def sans_ambiguite(texte: str) -> str:
    """Confond O et 0.

    En gras, les deux glyphes ont pratiquement le meme trace : le plus proche
    voisin tranche a quelques millemes de distance pres, et l'arbitrage peut
    basculer d'une version de numpy a l'autre. Comparer les libelles a O et 0
    confondus teste ce qui compte -- le texte est bien reconstruit -- sans
    dependre de ce tirage au sort. Les champs numeriques, eux, sont lus sans
    ambiguite : le parseur y force la lecture en chiffre.
    """
    return texte.replace('O', '0')


def jour(texte: str) -> date:
    j, m, a = (int(n) for n in texte.split('-'))
    return date(a, m, j)


# =========================================================================
# La propriete centrale : l'arithmetique du releve doit se refermer
# =========================================================================
def test_le_solde_se_reconstitue(depouille):
    """Solde initial + somme des operations = solde final imprime.

    C'est le controle qui donne sa valeur a l'outil : il tombe juste
    seulement si tous les montants ET tous les signes ont ete lus.
    """
    soldes, operations = depouille
    reconstitue = soldes[0]['montant'] + sum(op.montant for op in operations)
    assert round(reconstitue, 2) == soldes[-1]['montant']


def test_soldes_conformes_au_releve(depouille, attendu):
    soldes, _ = depouille
    assert len(soldes) == 2
    assert soldes[0]['montant'] == attendu['solde_initial']['montant']
    assert soldes[0]['date'] == jour(attendu['solde_initial']['date'])
    assert soldes[-1]['montant'] == attendu['solde_final']['montant']
    assert soldes[-1]['date'] == jour(attendu['solde_final']['date'])
    assert {s['devise'] for s in soldes} == {'EUR'}


# =========================================================================
# Aucune operation perdue, aucune inventee
# =========================================================================
def test_toutes_les_operations_sont_la(depouille, attendu):
    _, operations = depouille
    assert [op.numero for op in operations] == [o['numero'] for o in attendu['operations']]


def test_montants_et_dates_exacts(depouille, attendu):
    _, operations = depouille
    for op, ref in zip(operations, attendu['operations']):
        assert op.montant == ref['montant'], f'operation {op.numero}'
        assert op.date_operation == jour(ref['date']), f'operation {op.numero}'
        assert op.date_valeur == jour(ref['date_valeur']), f'operation {op.numero}'


def test_libelles_restitues_a_l_identique(depouille, attendu):
    _, operations = depouille
    for op, ref in zip(operations, attendu['operations']):
        assert ([sans_ambiguite(l) for l in op.lignes]
                == [sans_ambiguite(l) for l in ref['lignes']]), f'operation {op.numero}'


def test_aucun_caractere_non_reconnu(lignes):
    """Un glyphe absent du modele ressort en '?' : il ne doit pas y en avoir."""
    fautives = [texte for _, _, texte in lignes if '?' in texte]
    assert fautives == []


def test_operations_reparties_sur_plusieurs_pages(depouille):
    """Le releve d'exemple tient sur deux pages : le decoupage doit tenir."""
    _, operations = depouille
    assert len({op.page for op in operations}) > 1


# =========================================================================
# Reconstruction des libelles
# =========================================================================
def test_nom_coupe_sur_son_trait_d_union_est_recolle(depouille):
    """'BASIC-' + 'FIT' doit redonner 'BASIC-FIT', sans espace parasite.

    La banque coupe ses lignes sur le trait d'union : recoller avec une espace
    rendrait le beneficiaire introuvable pour les regles de classement.
    """
    _, operations = depouille
    coupees = [op for op in operations if 'BASIC' in op.description]
    assert coupees, "l'operation a nom coupe a disparu du releve d'exemple"
    assert 'BASIC-FIT BRUXELLES' in coupees[0].description


def test_lignes_jointes_par_une_espace(depouille):
    """Hors mot coupe, deux lignes se recollent avec une espace, pas collees."""
    _, operations = depouille
    op = next(o for o in operations if o.numero == '0007')
    assert 'COMMUNICATION : LOYER JUILLET 2026' in op.description


@pytest.mark.parametrize('numero, type_attendu', [
    ('0001', 'Achat OPC'),
    ('0005', 'Paiement Bancontact'),
    ('0006', 'Domiciliation'),
    ('0007', 'Ordre permanent'),
    ('0008', 'Paiement Mastercard'),
    ('0010', 'Virement'),
    ('0012', 'Frais de gestion'),
    ('0013', 'Releve Mastercard'),
    ('0014', 'Virement instantane'),
    ('0015', 'Virement Wero'),
    ('0017', 'Versement recu'),
    ('0018', 'Versement instantane recu'),
])
def test_type_deduit_du_libelle(depouille, numero, type_attendu):
    _, operations = depouille
    op = next(o for o in operations if o.numero == numero)
    assert op.type == type_attendu


def test_sens_coherent_avec_le_signe(depouille):
    _, operations = depouille
    for op in operations:
        assert op.sens == ('Credit' if op.montant > 0 else 'Debit')


def test_le_compte_du_titulaire_n_est_pas_une_contrepartie(depouille, attendu):
    """L'IBAN du releve apparait dans certains libelles : il doit etre ecarte."""
    _, operations = depouille
    titulaire = attendu['compte']
    assert any(titulaire in op.description for op in operations), \
        "le releve d'exemple ne cite plus l'IBAN du titulaire"
    assert all(op.iban_contrepartie != titulaire for op in operations)

    virement = next(o for o in operations if o.numero == '0010')
    assert virement.iban_contrepartie == 'BE62 5100 0754 7061'


def test_champs_extraits_du_libelle(depouille):
    _, operations = depouille
    par_numero = {op.numero: op for op in operations}

    domiciliation = par_numero['0006']
    assert domiciliation.communication == '+++123/4567/89012+++'
    assert domiciliation.reference == 'FT2026070400123'

    bancontact = par_numero['0005']
    assert bancontact.contrepartie == 'SUPERMARCHE EXEMPLE'
    assert bancontact.carte == '6703 12XX XXXX 3456'


def test_les_champs_numeriques_ne_souffrent_pas_de_l_ambiguite(depouille):
    """La confusion O/0 ne doit jamais atteindre un numero, une date ou un
    montant : le parseur y force la lecture en chiffre avant de convertir."""
    soldes, operations = depouille
    assert all(op.numero.isdigit() for op in operations)
    assert all(isinstance(op.montant, float) for op in operations)
    assert all(op.date_operation.year == 2026 for op in operations)
    assert all(s['date'].year == 2026 for s in soldes)


# =========================================================================
# Cas d'erreur
# =========================================================================
def test_pdf_sans_trace_vectoriel(tmp_path):
    """Un PDF qui n'est pas un releve doit echouer en le disant."""
    from tools.faire_releve_exemple import ecrire_pdf

    vide = tmp_path / 'vide.pdf'
    ecrire_pdf([[]], {}, {'pas': 5.971, 'origine': 5.399},
               {'largeur': 595.32, 'hauteur': 841.92}, vide)

    with pytest.raises(ValueError, match='aucun trace vectoriel'):
        ex.read_text(vide)


def test_releve_sans_ligne_de_solde(depouille):
    """Sans les deux lignes SOLDE, l'extraction n'a rien a controler."""
    soldes, _ = ex.parse([(1, ex.COL_DETAIL, 'BANCONTACT - ACHAT - EXEMPLE')])
    assert soldes == []


def test_fichier_absent():
    with pytest.raises(FileNotFoundError):
        ex.read_text('releve_qui_n_existe_pas.pdf')
