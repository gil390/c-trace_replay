# c_trace_replay

## Objectif

L'objectif du projet est de développer un outil capable d'analyser automatiquement une fonction C afin d'identifier ses dépendances, ses entrées, ses sorties et ses effets de bord.

À partir de cette analyse, l'outil génère automatiquement les mécanismes nécessaires pour observer le comportement réel de la fonction, capturer des cas de test représentatifs et les rejouer ultérieurement.

Ces cas de test permettent de vérifier automatiquement qu'une implémentation reproduit un comportement fonctionnel équivalent, indépendamment de son implémentation interne.

L'analyse automatique doit être privilégiée autant que possible. Les informations complémentaires ne doivent être demandées que lorsque certaines dépendances ou certains accès mémoire ne peuvent pas être déterminés avec un niveau de confiance suffisant.

---

## Principe général

Le projet repose sur cinq étapes principales :

### 1. Analyse

Analyse statique de la fonction cible afin d'identifier :

* les paramètres ;
* les valeurs de retour ;
* les variables globales lues et écrites ;
* les accès mémoire ;
* les structures manipulées ;
* les fonctions appelées ;
* les dépendances transitives.

### 2. Construction du modèle comportemental

À partir de l'analyse, l'outil construit :

* un ensemble des données lues (`read_set`) ;
* un ensemble des données modifiées (`write_set`) ;
* un graphe de dépendances ;
* une liste des ambiguïtés éventuelles.

### 3. Génération automatique

L'outil génère automatiquement :

* les mécanismes de capture ;
* les mécanismes de rejeu ;
* les programmes de test nécessaires ;
* les comparateurs de résultats.

### 4. Capture

La fonction est exécutée dans son environnement normal.

Les données nécessaires à la reproduction du comportement sont automatiquement enregistrées.

### 5. Rejeu et validation

Les données capturées sont réinjectées dans une implémentation à vérifier.

L'outil compare automatiquement :

* les valeurs de retour ;
* les sorties ;
* les états modifiés ;
* les effets de bord observables.

Le résultat est exprimé sous la forme :

```text
PASS
```

ou

```text
FAIL
```

---

## Philosophie du projet

Le projet vise à minimiser l'intervention humaine.

L'objectif n'est pas de décrire manuellement les entrées, sorties ou dépendances d'une fonction, mais de les découvrir automatiquement à partir du code source.

Les informations complémentaires ne doivent être demandées que lorsqu'une ambiguïté réelle empêche la construction d'un mécanisme de capture ou de rejeu fiable.

---

## Utilisation

### Analyse d'une fonction

```bash
make show-report FUNC=<fonction>
```

### Affichage des ambiguïtés détectées

```bash
make show-warnings FUNC=<fonction>
```

### Génération des mécanismes de capture et de rejeu

```bash
make generate FUNC=<fonction>
```

### Capture et rejeu

```bash
make test FUNC=<fonction>
```

---

## Sorties produites

L'outil génère notamment :

* un rapport d'analyse ;
* une description des dépendances détectées ;
* une liste d'ambiguïtés éventuelles ;
* les programmes de capture ;
* les programmes de rejeu ;
* les données capturées ;
* les résultats de comparaison.

---

## Limites actuelles

Certaines situations restent difficiles à analyser automatiquement :

* structures dynamiques complexes ;
* listes chaînées ;
* graphes ;
* callbacks indirects ;
* accès mémoire dépendants du contenu ;
* dépendances externes non visibles dans le code source.

Ces cas sont signalés explicitement afin d'éviter toute conclusion erronée.

---

## Vision long terme

À terme, l'outil doit être capable de construire automatiquement un modèle comportemental complet d'une fonction C, de générer les mécanismes nécessaires à son observation, puis de vérifier l'équivalence fonctionnelle d'implémentations différentes à partir du comportement observé plutôt que de leur structure interne.

---

## État actuel du prototype

Le prototype actuel analyse le code C avec Clang/libclang lorsque les dépendances
sont disponibles. Il produit un rapport JSON contenant notamment :

* la fonction analysée ;
* son type de retour ;
* ses paramètres ;
* les fonctions appelées ;
* les variables globales lues et écrites ;
* les ensembles `read_set` et `write_set` ;
* les captures déduites avant et après appel ;
* les ambiguïtés éventuelles dans `annotation_required`.

Le générateur de harness s'appuie ensuite sur deux sources :

* le rapport d'analyse `generated/<fonction>_report.json` ;
* un fichier de description de cas `testcases/<fonction>.case.json`.

Le fichier `.case.json` décrit les variables à instancier, les arguments à
passer à la fonction et les bindings entre les symboles détectés par l'analyseur
et les expressions C à sauvegarder ou comparer.

Le replay compare actuellement :

* la valeur de retour, si la fonction n'est pas `void` ;
* les zones mémoire associées au `write_set` ;
* les variables globales modifiées.

Les cas réellement ambigus restent volontairement bloquants. Par exemple, un
pointeur transmis à une fonction non analysée ou une boucle dépendante du contenu
mémoire peut produire une entrée dans `annotation_required`.

## Commandes pratiques

Analyser la fonction par défaut, `compute` :

```bash
make show-report
```

Analyser une autre fonction :

```bash
make show-report FUNC=toto
```

Afficher uniquement les ambiguïtés et annotations requises :

```bash
make show-warnings FUNC=compute
```

Générer les harness de capture/replay :

```bash
make generate FUNC=compute
```

Capturer puis rejouer un cas :

```bash
make test FUNC=compute
```

Tester le même pipeline sur `toto` :

```bash
make test FUNC=toto
```

Lancer la batterie de cas lecture/écriture/inout :

```bash
make test-rw-cases
```

Vérifier automatiquement plusieurs rapports JSON :

```bash
make test-reports
```

Nettoyer les fichiers générés :

```bash
make clean
```

Les principaux fichiers générés sont :

* `generated/<fonction>_report.json` ;
* `generated/<fonction>_annotations.required.json` ;
* `generated/harness_<fonction>_capture.c` ;
* `generated/harness_<fonction>_replay.c` ;
* `generated/capture_<fonction>` ;
* `generated/replay_<fonction>` ;
* `testcases/<fonction>_case_001/*.bin`.
