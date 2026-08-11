# Extracteur de relevé bancaire

[![CI](https://github.com/USER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/USER/REPO/actions/workflows/ci.yml)

[English (en)](README.md) · **Français (fr)**

Transforme un relevé de compte bancaire (PDF) en classeur Excel — sur des
relevés qui ne contiennent aucun texte.

## Le problème

Extraire les transactions d'un relevé bancaire devrait être un problème
résolu. Tous les outils renvoient une page blanche :

```console
$ pdftotext releve.pdf -

>>> pdfplumber.open("releve.pdf").pages[0].extract_text()
''
```

Neuf pages, quatre-vingt-sept transactions, et pas un seul caractère de
texte. Le PDF n'a strictement aucune couche texte : le générateur convertit
la police en contours avant d'écrire le fichier, si bien que chaque caractère
est stocké comme un ensemble de tracés vectoriels remplis. Il n'y a de « A »
nulle part dans le document — seulement la *forme* d'un A.

Pire : les contours sont requantifiés à chaque occurrence. Deux « A » sur la
même page ne sont jamais géométriquement identiques, donc les caractères ne
peuvent pas non plus être retrouvés en cherchant des tracés répétés.

## Pourquoi les réponses habituelles ne marchent pas

**L'extraction de texte** n'a rien à extraire. `pdftotext`, `pdfplumber` et
`pypdfium2` renvoient tous une chaîne vide, parce qu'ils demandent tous au
fichier un contenu qu'il ne porte pas.

**L'OCR** est le recours habituel : rastériser la page, lancer Tesseract. Ça
marcherait globalement. Mais ça jette une information qui est pourtant là —
la géométrie exacte de chaque glyphe — pour la remplacer par une estimation
statistique sur des pixels. Sur un relevé bancaire, le mode d'échec d'une
estimation est un montant faux en silence, exactement ce qu'on ne peut pas
tolérer.

Les contours, eux, sont exacts. La mise en page est monospace. C'est
suffisant pour décoder la page sans deviner.

## La démarche

1. **Les lignes.** Chaque tracé rempli de la page est collecté puis regroupé
   par ligne de base. Les jambages et les parenthèses descendent sous la
   ligne et créeraient de fausses lignes de base : les candidates à moins de
   5 pt l'une de l'autre sont donc repliées sur la mieux étayée.

2. **La grille.** Le relevé est composé dans une police monospace, donc la
   position des glyphes suit `origine + n × pas`. Les deux sont retrouvés en
   maximisant la moyenne circulaire de `x mod p` sur la plage de pas
   plausible — le vrai pas est celui pour lequel l'abscisse de chaque glyphe
   tombe en phase. Il ressort à environ 5,97 pt.

3. **Les empreintes.** Chaque cellule de la grille est rastérisée en
   suréchantillonnage ×8, et ses tracés sont composités en XOR — ce qui
   transforme la règle de remplissage pair-impair en compteur qui fonctionne
   réellement : les trous du « o », du « e » et du « 8 » ressortent sans
   effort supplémentaire. La cellule est ensuite sous-échantillonnée en
   12 × 18 et aplatie en un vecteur à 217 dimensions : 216 valeurs de
   couverture normalisées, plus un terme de quantité d'encre.

4. **La classification.** Plus proche voisin parmi 162 empreintes apprises.
   Une cellule trop éloignée de tout glyphe du modèle est rapportée comme
   `?` avec un avertissement, plutôt que d'être devinée.

5. **L'analyse.** Le texte reconstruit est un tableau à colonnes fixes, lu
   par expressions régulières : lignes de solde, en-têtes de transaction, et
   les lignes de description qui s'enroulent en dessous de chacune.

## Le relevé se contrôle lui-même

Ce qui rend cet outil fiable plutôt que simplement astucieux : l'extracteur
recalcule `solde initial + Σ montants` et compare le résultat au solde final
imprimé sur la dernière page.

```console
$ python extract_releve.py releve.pdf
87 operations, solde initial 1,581.47 EUR, solde final 3,863.03 EUR
Controle : OK
Ecrit -> releve.xlsx
```

« Controle : OK » signifie que chaque montant et chaque signe ont été lus
correctement — un seul chiffre mal reconnu casse l'arithmétique, et le dit.
C'est ce qui rend une reconnaissance de caractères maison acceptable pour de
la donnée financière : elle n'est pas crue sur parole, elle est vérifiée, à
chaque exécution.

Lors de son premier mois d'utilisation, ce contrôle a mis au jour trois
erreurs de saisie dans le classeur budget qu'il alimente.

## Installation

```console
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS : source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.11+. Quatre dépendances : `pdfplumber`, `numpy`, `Pillow`,
`openpyxl`.

## Utilisation

Extraire un relevé vers un classeur :

```console
python extract_releve.py releve.pdf [-o sortie.xlsx]
```

Le classeur compte une ligne par transaction — date, date valeur, numéro,
type, contrepartie, IBAN de la contrepartie, communication, référence,
carte, sens, débit, crédit, montant, solde courant, description brute,
page — encadrée par les lignes de solde initial et final.

`preremplir_budget.py` reporte ensuite ces transactions dans un classeur
budget mensuel, en donnant à chacune une description courte et une catégorie
issues d'un jeu de règles JSON. Il n'écrit rien par défaut ; `--ecrire`
applique les changements, après avoir pris une sauvegarde datée.

```console
python preremplir_budget.py releve.xlsx            # simulation, affiche un rapport
python preremplir_budget.py releve.xlsx --ecrire   # applique
```

Il écarte les transferts internes et le salaire, regroupe les échéances du
même jour d'un même achat, et détecte ce qui est déjà présent dans le
classeur (même montant à 5 jours près) pour qu'une relance ne duplique
jamais rien. Ce qui n'est reconnu par aucune règle part en catégorie
`À CLASSER` plutôt que d'être forcé dans une case qui ne convient pas.

## Tests

```console
pip install -r requirements-dev.txt
pytest -v
```

**Aucun relevé réel n'existe dans ce dépôt, et il n'y en a jamais eu.** Les
tests tournent sur un relevé entièrement synthétique, construit en deux
temps :

- `tools/extraire_glyphes.py` prélève sur un relevé réel, gardé hors du
  dépôt, une *bibliothèque de glyphes* — pour chaque caractère, les contours
  vectoriels d'une occurrence, exprimés relativement à sa cellule. C'est de
  la géométrie de police et rien d'autre : le contour d'un « A » reste un
  « A », quel que soit le relevé dont il provient.
- `tools/faire_releve_exemple.py` redessine ces contours dans un nouveau PDF
  à partir d'un contenu entièrement inventé — `tests/data/releve_exemple.json`,
  avec des noms, des commerçants et des montants fictifs, et les IBAN que les
  banques publient elles-mêmes comme exemples.

Le résultat est un PDF qui a la même propriété que l'original — aucune
couche texte, chaque caractère en contours — et dont le contenu attendu est
connu avec exactitude. Les tests vérifient que l'extracteur le retrouve : le
solde se reconstitue, aucune transaction n'est perdue, les libellés
reviennent à l'identique, et chaque type de transaction est correctement
classé.

Un job de CI refuse en plus tout commit portant un PDF ou un classeur autre
que l'exemple.

## Limites connues

- **`O` et `0` ont la même forme.** Dans cette police en gras, la lettre et
  le chiffre sont dessinés de façon identique, et aucune finesse d'empreinte
  ne les sépare : le classificateur tranche à un cheveu près, et se trompe
  parfois. Ça n'a pas d'importance là où ça compte — les champs numériques
  forcent une lecture en chiffre avant l'analyse — mais un libellé peut
  revenir sous la forme `S0LDE`.
- **Une banque, une mise en page.** Les positions de colonnes, les lignes de
  solde et la grammaire des transactions sont propres à la banque émettrice.
  Une autre banque impose un autre analyseur.
- **Le modèle couvre ce qu'il a vu.** Un caractère absent des 162 empreintes
  est rapporté comme `?` avec un avertissement ; la solution est de
  réentraîner le modèle, pas de rafistoler l'analyse.

## Organisation du dépôt

```
extract_releve.py       PDF -> classeur : decodage, analyse, export Excel
preremplir_budget.py    classeur -> classeur budget mensuel
regles_categories.json  regles de classement d'exemple (les votres vont dans un fichier .local.)
glyph_model.npz         162 empreintes de glyphes
tools/                  fabrication du releve d'exemple synthetique
tests/                  la suite, et l'exemple sur lequel elle tourne
```

## Notes de développement

L'algorithme d'extraction — empreintes de glyphes, ajustement de la grille,
contrôle de solde — est un travail original, développé et validé sur des
relevés réels avant l'existence de ce dépôt. Le dépôt qui l'entoure — suite
de tests, pipeline CI, packaging, documentation et données d'exemple
anonymisées — a été structuré avec l'assistance d'outils d'IA, pour rendre
le code plus simple à installer, à vérifier et à comprendre.

## Licence

MIT — voir [LICENSE](LICENSE).
