"""Fabrique le releve d'exemple utilise par les tests.

Le contenu vient de tests/data/releve_exemple.json (entierement invente), la
forme des caracteres de tests/data/glyphes.json (geometrie de police seule).
Le PDF produit est donc, comme un vrai releve bancaire, depourvu de couche
texte : chaque caractere y est dessine en contours vectoriels.

    python tools/faire_releve_exemple.py

C'est ce fichier qui sert de reference aux tests de bout en bout : il permet
de valider la chaine complete sans qu'aucun releve reel n'entre dans le depot.
"""
from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path

DONNEES = Path(__file__).resolve().parent.parent / 'tests' / 'data'

# --- mise en page, relevee sur un vrai releve -----------------------------
COL_RECORD = 14           # colonne des soldes et des en-tetes d'operation
COL_DETAIL = 16           # colonne des lignes de detail
LARGEUR_RECORD = 73       # colonnes 14 a 86
LARGEUR_DETAIL = 54       # colonnes 16 a 69
COL_SIGNE = 64            # position du + / - dans une ligne de record
INTERLIGNE = 11.87
BAS_DE_PAGE = 788.0

# page 1 : bloc adresse, puis le tableau
Y_ENTETE_1 = [98.23, 133.96, 145.79, 157.71, 169.83]
Y_SEPARATEUR_1 = 252.85
Y_PREMIERE_1 = 276.52
# pages suivantes : ligne de rappel, separateur, puis le tableau
Y_ENTETE_N = 98.20
Y_SEPARATEUR_N = 133.90
Y_PREMIERE_N = 157.60


def montant(v: float) -> tuple[str, str]:
    """-> (signe, montant formate a la belge) : 1234.5 -> ('+', '1.234,50')."""
    signe = '+' if v >= 0 else '-'
    formate = f'{abs(v):,.2f}'.replace(',', '@').replace('.', ',').replace('@', '.')
    return signe, formate


def ligne_record(gauche: str, valeur: float) -> str:
    signe, m = montant(valeur)
    return f'{gauche:<{COL_SIGNE}}{signe}{m:>{LARGEUR_RECORD - COL_SIGNE - 1}}'


def ligne_solde(solde: dict) -> str:
    gauche = f"SOLDE AU   {solde['date']}"
    if solde.get('heure'):
        gauche += f" {solde['heure']}"
    return ligne_record(f'{gauche:<41}EUR', solde['montant'])


def ligne_operation(op: dict) -> str:
    gauche = (f"{op['numero']}  {op['date']}  (VAL. {op['date_valeur']})")
    return ligne_record(gauche, op['montant'])


def separateur(compte: str, premiere_page: bool) -> str:
    if premiere_page:
        milieu = f'  {compte}  BIC: EXBKBEBB  '
        gauche = 17
    else:
        milieu = f'  {compte}  '
        gauche = 25
    droite = LARGEUR_RECORD - gauche - len(milieu)
    return '-' * gauche + milieu + '-' * droite


# =========================================================================
# 1. Composition : de la description du releve aux lignes placees
# =========================================================================
def composer(releve: dict) -> list[list[tuple[int, float, str]]]:
    """-> une liste de pages, chacune une liste de (colonne, baseline, texte)."""
    compte = releve['compte']

    def bloc(op: dict) -> list[tuple[int, str]]:
        return ([(COL_RECORD, ligne_operation(op))]
                + [(COL_DETAIL, ligne) for ligne in op['lignes']])

    pages: list[list[tuple[int, float, str]]] = []
    page: list[tuple[int, float, str]] = []
    y = 0.0

    def nouvelle_page() -> None:
        nonlocal page, y
        page = []
        pages.append(page)
        if len(pages) == 1:
            textes = [(70, 'COMPTE COURANT'),
                      (COL_RECORD, releve['titulaire']),
                      (COL_RECORD, f"{releve['adresse'][0]:<50}DATE :       "
                                   f"{releve['date_releve']}"),
                      (COL_RECORD, releve['adresse'][1]),
                      (64, f"PAGE :              {len(pages)}/{{total}}")]
            for (col, texte), base in zip(textes, Y_ENTETE_1):
                page.append((col, base, texte))
            page.append((COL_RECORD, Y_SEPARATEUR_1, separateur(compte, True)))
            y = Y_PREMIERE_1
        else:
            page.append((45, Y_ENTETE_N,
                         f"{releve['date_releve']:<39}{len(pages)}/{{total}}"))
            page.append((COL_RECORD, Y_SEPARATEUR_N, separateur(compte, False)))
            y = Y_PREMIERE_N

    def poser(lignes: list[tuple[int, str]]) -> None:
        """Pose un bloc insecable, en changeant de page s'il ne tient pas."""
        nonlocal y
        if y + (len(lignes) - 1) * INTERLIGNE > BAS_DE_PAGE:
            nouvelle_page()
        for col, texte in lignes:
            page.append((col, y, texte))
            y += INTERLIGNE
        y += INTERLIGNE          # une ligne blanche entre les operations

    nouvelle_page()
    poser([(COL_RECORD, ligne_solde(releve['solde_initial']))])
    for op in releve['operations']:
        poser(bloc(op))
    poser([(COL_RECORD, ligne_solde(releve['solde_final']))])
    poser([(COL_RECORD, 'CE PRODUIT EST PROTEGE PAR LA GARANTIE BANCAIRE DES DEPOTS.'),
           (COL_RECORD, "PLUS D'INFOS AUPRES DE VOTRE BANQUE OU EN AGENCE.")])

    total = len(pages)
    return [[(col, base, texte.replace('{total}', str(total)))
             for col, base, texte in p] for p in pages]


def verifier(pages: list[list[tuple[int, float, str]]], glyphes: dict) -> None:
    manquants = set()
    for page in pages:
        for col, _, texte in page:
            largeur = LARGEUR_RECORD if col <= COL_RECORD else LARGEUR_DETAIL
            if col in (COL_RECORD, COL_DETAIL) and len(texte) > largeur:
                raise SystemExit(f'ligne trop longue ({len(texte)} > {largeur}) : {texte!r}')
            manquants |= {c for c in texte if c != ' ' and c not in glyphes}
    if manquants:
        raise SystemExit('caracteres absents de la bibliotheque de glyphes : '
                         + ' '.join(sorted(manquants)))


# =========================================================================
# 2. Ecriture du PDF
# =========================================================================
def flux_page(page, glyphes: dict, grille: dict, hauteur: float) -> bytes:
    """Contenu graphique d'une page : un chemin ferme par contour de glyphe."""
    pas, origine = grille['pas'], grille['origine']
    morceaux = ['0 g']
    for col0, base, texte in page:
        for i, car in enumerate(texte):
            contours = glyphes.get(car)
            if not contours:
                continue                       # espace
            x = origine + (col0 + i) * pas
            for contour in contours:
                debut = True
                for dx, dy in contour:
                    op = 'm' if debut else 'l'
                    morceaux.append(f'{x + dx:.2f} {hauteur - (base + dy):.2f} {op}')
                    debut = False
                morceaux.append('h')
            # remplissage pair-impair : les contre-formes (o, e, 8) font des trous
            morceaux.append('f*')
    return '\n'.join(morceaux).encode('latin-1')


def ecrire_pdf(pages, glyphes, grille, page_size, chemin: Path) -> None:
    largeur, hauteur = page_size['largeur'], page_size['hauteur']
    objets: list[bytes] = []

    def ajouter(corps: bytes) -> int:
        objets.append(corps)
        return len(objets)

    ajouter(b'')                                    # 1 : catalogue (rempli plus bas)
    ajouter(b'')                                    # 2 : arbre des pages
    ids_pages = []
    for page in pages:
        flux = zlib.compress(flux_page(page, glyphes, grille, hauteur), 9)
        contenu = ajouter(b'<< /Length %d /Filter /FlateDecode >>\nstream\n' % len(flux)
                          + flux + b'\nendstream')
        ids_pages.append(ajouter(
            b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] '
            b'/Resources << >> /Contents %d 0 R >>' % (largeur, hauteur, contenu)))

    objets[0] = b'<< /Type /Catalog /Pages 2 0 R >>'
    kids = b' '.join(b'%d 0 R' % i for i in ids_pages)
    objets[1] = (b'<< /Type /Pages /Count %d /Kids [%s] >>' % (len(ids_pages), kids))

    sortie = bytearray(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n')
    decalages = []
    for numero, corps in enumerate(objets, start=1):
        decalages.append(len(sortie))
        sortie += b'%d 0 obj\n' % numero + corps + b'\nendobj\n'

    xref = len(sortie)
    sortie += b'xref\n0 %d\n' % (len(objets) + 1)
    sortie += b'0000000000 65535 f \n'
    for d in decalages:
        sortie += b'%010d 00000 n \n' % d
    sortie += (b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'
               % (len(objets) + 1, xref))

    chemin.write_bytes(bytes(sortie))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--releve', type=Path, default=DONNEES / 'releve_exemple.json')
    ap.add_argument('--glyphes', type=Path, default=DONNEES / 'glyphes.json')
    ap.add_argument('-o', '--out', type=Path, default=DONNEES / 'releve_exemple.pdf')
    args = ap.parse_args()

    releve = json.loads(args.releve.read_text(encoding='utf-8'))
    biblio = json.loads(args.glyphes.read_text(encoding='utf-8'))

    pages = composer(releve)
    verifier(pages, biblio['glyphes'])
    ecrire_pdf(pages, biblio['glyphes'], biblio['grille'], biblio['page'], args.out)

    print(f'{len(pages)} page(s), {len(releve["operations"])} operations '
          f'-> {args.out} ({args.out.stat().st_size / 1024:.0f} Ko)')


if __name__ == '__main__':
    main()
