"""Classement des operations et detection de ce qui est deja saisi.

Les regles utilisees ici sont celles du jeu d'exemple versionne, jamais les
regles personnelles : les tests doivent donner le meme resultat partout.
"""
from __future__ import annotations

from datetime import datetime

import pytest

import extract_releve as ex
import preremplir_budget as pb


@pytest.fixture(scope='session')
def regles():
    return pb.charger_regles(pb.REGLES_EXEMPLE)


@pytest.fixture(scope='session')
def operations(depouille, tmp_path_factory, regles):
    """Le releve d'exemple, exporte puis relu par preremplir_budget."""
    soldes, ops = depouille
    chemin = tmp_path_factory.mktemp('budget') / 'releve.xlsx'
    ex.to_excel(soldes, ops, chemin)
    lues = pb.lire_releve(chemin)
    pb.classer(lues, regles)
    return lues


def par_description(ops, fragment):
    return [o for o in ops if fragment.lower() in o.description.lower()]


# =========================================================================
# Classement
# =========================================================================
def test_les_depenses_sont_comptees_positivement(operations):
    """Le releve compte a l'envers du budget : un debit devient une depense."""
    achats = par_description(operations, 'investissement')
    assert achats and all(o.montant > 0 for o in achats)
    salaire = [o for o in operations if o.montant < 0]
    assert salaire, 'aucune rentree dans le releve d\'exemple'


def test_une_regle_a_montants_choisit_selon_le_montant(operations):
    telecom = par_description(operations, 'abonnement mobile')
    assert len(telecom) == 1
    assert telecom[0].montant == 35.00
    assert telecom[0].categorie == 'Abonnements'
    assert telecom[0].verifier is False


def test_une_regle_large_regarde_la_description_complete(operations):
    """« RETRAIT D'ESPECES » n'apparait que dans la description, pas dans le
    triplet Type | Contrepartie | Communication : sans `large`, rien ne matche."""
    retraits = par_description(operations, 'retrait')
    assert len(retraits) == 1
    assert retraits[0].montant == 70.00
    assert retraits[0].verifier is True


def test_ce_qui_n_est_pas_reconnu_part_a_classer(operations):
    inconnues = [o for o in operations if o.categorie == pb.A_CLASSER]
    assert inconnues, 'le releve d\'exemple ne teste plus le repli'
    assert all(o.description for o in inconnues)


def test_aucune_categorie_hors_regles(operations, regles):
    connues = {r.categorie for r in regles if r.categorie} | {pb.A_CLASSER}
    assert {o.categorie for o in operations if o.statut != 'ignore'} <= connues


# =========================================================================
# Agregation
# =========================================================================
def test_les_achats_opc_du_meme_jour_sont_regroupes(operations):
    avant = par_description(operations, 'investissement')
    assert len(avant) == 4 and all(o.montant == 50.00 for o in avant)

    apres = par_description(pb.agreger(operations), 'investissement')
    assert len(apres) == 1
    assert apres[0].montant == 200.00
    assert apres[0].detail == 'lignes du jour regroupees'


def test_l_agregation_ne_touche_pas_les_autres_lignes(operations):
    autres_avant = [o for o in operations if not (o.regle and o.regle.agreger)]
    autres_apres = [o for o in pb.agreger(operations) if not (o.regle and o.regle.agreger)]
    assert len(autres_avant) == len(autres_apres)


# =========================================================================
# Doublons
# =========================================================================
def test_une_ligne_deja_saisie_n_est_pas_reproposee(operations):
    ops = pb.agreger(list(operations))
    cible = par_description(ops, 'abonnement mobile')[0]
    deja = [(cible.date, cible.montant)]

    pb.marquer_doublons(ops, deja)
    assert cible.statut == 'doublon'
    assert 'deja saisi' in cible.detail


def test_un_montant_voisin_est_signale_mais_pas_ajoute(operations):
    ops = pb.agreger(list(operations))
    cible = par_description(ops, 'abonnement mobile')[0]
    voisin = [(cible.date, round(cible.montant + 0.50, 2))]

    pb.marquer_doublons(ops, voisin)
    assert cible.statut == 'doublon?'
    assert 'proche de' in cible.detail


def test_une_saisie_existante_n_absorbe_qu_une_seule_operation(regles):
    """Deux depenses identiques, une seule deja saisie : une seule est ecartee."""
    ops = [pb.Operation(date=datetime(2026, 7, 2), montant=50.0, texte='X',
                        texte_large='X', contrepartie='', apercu='X')
           for _ in range(2)]
    pb.marquer_doublons(ops, [(datetime(2026, 7, 2), 50.0)])
    assert sorted(o.statut for o in ops) == ['ajout', 'doublon']


def test_un_ecart_de_date_trop_grand_ne_fait_pas_doublon():
    op = pb.Operation(date=datetime(2026, 7, 20), montant=50.0, texte='X',
                      texte_large='X', contrepartie='', apercu='X')
    pb.marquer_doublons([op], [(datetime(2026, 7, 1), 50.0)])
    assert op.statut == 'ajout'
