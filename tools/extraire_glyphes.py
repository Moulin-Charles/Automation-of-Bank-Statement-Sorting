"""Extrait d'un vrai releve la bibliotheque de contours de glyphes.

Le fichier produit (tests/data/glyphes.json) ne contient QUE de la geometrie
de police : pour chaque caractere, les contours vectoriels d'une occurrence,
exprimes relativement a sa cellule de la grille. Aucun texte, aucun montant,
aucune donnee nominative n'y figure -- un contour de << A >> reste un << A >>
quel que soit le releve dont il vient.

C'est cette bibliotheque qui permet a tools/faire_releve_exemple.py de
fabriquer un releve entierement invente que extract_releve.py sait relire.

A lancer une seule fois, sur un releve reel garde hors du depot :

    python tools/extraire_glyphes.py chemin/vers/releve.pdf
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pdfplumber

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import extract_releve as ex  # noqa: E402

SORTIE = Path(__file__).resolve().parent.parent / 'tests' / 'data' / 'glyphes.json'


def extraire(pdf_path: Path) -> dict:
    model = np.load(ex.MODEL, allow_pickle=True)
    centroids, chars = model['centroids'], model['chars']

    with pdfplumber.open(pdf_path) as pdf:
        pages = [ex._components(p) for p in pdf.pages]
        largeur, hauteur = pdf.pages[0].width, pdf.pages[0].height
    pitch, origin = ex._fit_grid([c['x0'] for pg in pages for c in pg])

    # meilleur exemplaire par caractere : celui dont l'empreinte est la plus
    # proche du centroide du modele, donc le plus canonique
    meilleurs: dict[str, tuple[float, list]] = {}
    for comps in pages:
        for base, line in ex._lines(comps):
            cells: dict[int, list] = {}
            for c in line:
                cells.setdefault(int(round((c['x0'] - origin) / pitch)), []).append(c)
            for col, cs in cells.items():
                cell_x = origin + col * pitch
                f = ex._raster(cs, cell_x, base, pitch)
                d = np.linalg.norm(centroids - f, axis=1)
                j = int(d.argmin())
                if d[j] > ex.MAX_DIST:
                    continue
                car = str(chars[j])
                if car in meilleurs and meilleurs[car][0] <= d[j]:
                    continue
                contours = [[[round(x - cell_x, 3), round(y - base, 3)] for x, y in c['pts']]
                            for c in cs]
                meilleurs[car] = (float(d[j]), contours)

    return {
        'page': {'largeur': round(largeur, 3), 'hauteur': round(hauteur, 3)},
        'grille': {'pas': round(float(pitch), 4), 'origine': round(float(origin), 4)},
        'glyphes': {car: contours for car, (_, contours) in sorted(meilleurs.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('pdf', type=Path, help='releve reel servant de source de contours')
    ap.add_argument('-o', '--out', type=Path, default=SORTIE)
    args = ap.parse_args()

    biblio = extraire(args.pdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(biblio, ensure_ascii=False, indent=1), encoding='utf-8')

    glyphes = biblio['glyphes']
    print(f'{len(glyphes)} glyphes -> {args.out}')
    print('caracteres :', ''.join(sorted(glyphes)))


if __name__ == '__main__':
    main()
