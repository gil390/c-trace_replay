# c_trace_replay_v3

Ce projet demontre un workflow de capture/replay pour une fonction C.

L'objectif est de reduire le besoin d'un fichier `annotations.json` manuel :
l'analyseur deduit automatiquement les donnees lues et ecrites par la fonction
cible, puis ne demande des annotations que lorsqu'une ambiguite reste impossible
a resoudre automatiquement.

## Fonctionnement general

Le pipeline suit ces etapes :

1. analyser le code C de la fonction cible ;
2. deduire les `read_set` et `write_set` ;
3. produire un rapport d'analyse complet ;
4. produire une liste d'annotations requises uniquement en cas d'ambiguite ;
5. generer un harness de capture si aucune annotation bloquante n'est requise ;
6. executer la fonction cible et sauvegarder les donnees utiles ;
7. generer ou compiler un harness de replay ;
8. rejouer le cas capture ;
9. comparer le resultat obtenu avec le resultat attendu.

Dans l'exemple fourni, la fonction cible est `compute()` dans
`examples/sample.c`.

## Commandes utiles

Compiler et executer l'exemple simple :

```bash
make sample-run
```

Lancer l'analyse et afficher le rapport complet :

```bash
make show-report
```

Afficher les warnings et annotations eventuellement requises :

```bash
make show-warnings
```

Lancer le workflow complet capture + replay :

```bash
make test
```

Resultat attendu :

```text
CAPTURE OK: testcase written in testcases/case_001
REPLAY PASS
```

Nettoyer les binaires et donnees generees :

```bash
make clean
```

## Fichiers importants

- `examples/sample.c` : implementation de la fonction `compute()`.
- `examples/sample.h` : declarations, types et variables globales.
- `examples/sample_main.c` : programme minimal d'execution directe.
- `tools/analyze.py` : analyseur actuel, base sur des heuristiques simples.
- `tools/generate_harness.py` : generation des programmes de capture/replay.
- `generated/<fonction>_report.json` : rapport d'analyse complet.
- `generated/<fonction>_annotations.required.json` : warnings et annotations a fournir si besoin.
- `generated/harness_compute_capture.c` : harness de capture genere.
- `generated/harness_compute_replay.c` : harness de replay genere.
- `testcases/case_001/` : donnees binaires capturees pour le replay.

## Role de `<fonction>_annotations.required.json`

`<fonction>_annotations.required.json` n'est pas une configuration obligatoire du projet.

Ce fichier est une sortie de l'analyseur. Il sert a indiquer ce que l'analyse
automatique ne sait pas deduire avec certitude : taille d'un pointeur, direction
`in` / `out` / `inout`, boucle dependante du contenu memoire, appel de fonction
non analyse, etc.

Si `annotation_required` est vide, la generation du harness peut continuer.
Si des annotations sont presentes, la generation s'arrete afin d'eviter de
capturer ou rejouer un etat incomplet.

## Etat actuel de l'analyseur

L'analyseur actuel dans `tools/analyze.py` tente d'abord d'utiliser
Clang/libclang pour parcourir un vrai AST C. Si les dependances Clang ne sont
pas disponibles, il bascule temporairement sur l'ancien analyseur par
expressions regulieres afin de ne pas casser le workflow existant.

Le backend utilise est indique a l'execution :

```text
backend: clang
```

ou, si Clang n'est pas encore installe :

```text
backend: regex-fallback
```

Il sait notamment detecter dans des cas simples :

- les parametres de la fonction cible ;
- certains appels de fonctions ;
- les lectures de tableaux comme `input[i]` ;
- les ecritures de tableaux comme `output[i]` ;
- les acces a des champs de structure comme `ctx->scale` ;
- les lectures et ecritures de variables globales comme `g_mode` ou `g_counter`.

Ses limites principales sont :

- le backend Clang doit etre installe pour obtenir une vraie analyse AST ;
- gestion fragile des macros et typedefs complexes ;
- analyse limitee des expressions multi-lignes ;
- pas d'analyse interprocedurale complete ;
- detection approximative du contexte lecture/ecriture ;
- generation de harness encore specialisee pour `compute()`.

## Passage a un vrai AST C avec Clang

Pour faire evoluer le projet vers du code C reel, `tools/analyze.py` contient
une premiere implementation basee sur Clang/libclang. Elle sera utilisee
automatiquement lorsque les dependances seront installees.

Clang fournit un AST C fiable : il comprend les types, les declarations, les
fonctions, les expressions, les appels, les acces tableaux, les champs de
structures, les variables globales et les informations issues du preprocessing.

Sur Arch Linux, installer Clang cote systeme :

```bash
sudo pacman -S clang
```

Puis installer les bindings Python dans le virtualenv du projet :

```bash
source venv/bin/activate
pip install -r requirements.txt
```

Verifier que l'import Python fonctionne :

```bash
python -c "from clang.cindex import Index; print('libclang OK')"
```

Si les bindings sont installes dans le virtualenv, lancer les commandes `make`
avec ce Python :

```bash
make show-report PYTHON=venv/bin/python
```

Si Python ne trouve pas automatiquement `libclang.so`, l'analyseur essaie deja
plusieurs chemins courants, dont :

```text
/usr/lib/libclang.so
/usr/lib/llvm/lib/libclang.so
/usr/lib/llvm-18/lib/libclang.so
```

L'objectif est de conserver le meme contrat JSON qu'aujourd'hui :

- `parameters`
- `globals_read`
- `globals_written`
- `calls`
- `access_sets.read_set`
- `access_sets.write_set`
- `inferred_captures.before`
- `inferred_captures.after`
- `warnings`
- `annotation_required`

Ainsi, `tools/generate_harness.py` pourra continuer a consommer le rapport
`generated/<fonction>_report.json` sans changement majeur pendant la migration.

## Etapes conseillees pour migrer vers Clang

1. Ajouter une dependance Python `clang` au projet.
2. Creer une premiere version AST de `tools/analyze.py`.
3. Trouver la fonction cible dans l'AST par son nom.
4. Extraire les parametres depuis les noeuds `PARM_DECL`.
5. Parcourir le corps de la fonction cible.
6. Detecter les appels via les noeuds `CALL_EXPR`.
7. Detecter les acces tableaux via les noeuds `ARRAY_SUBSCRIPT_EXPR`.
8. Detecter les champs de structure via les noeuds `MEMBER_REF_EXPR`.
9. Identifier les variables globales en distinguant leur declaration d'origine.
10. Determiner le contexte lecture/ecriture autour des affectations.
11. Generer les memes fichiers JSON que la version actuelle.
12. Ajouter des cas de test C plus complexes pour valider l'analyse.

Les cas incertains doivent continuer a produire des warnings ou des entrees dans
`annotation_required`, par exemple lorsqu'un pointeur est transmis a une fonction
non analysee ou lorsqu'une taille de buffer ne peut pas etre deduite.

## Sorties generees

Apres `make test`, le dossier `testcases/case_001/` contient les donnees
necessaires au replay :

- `ctx_before.bin`
- `input_before.bin`
- `g_mode_before.bin`
- `g_counter_before.bin`
- `output_expected.bin`
- `g_counter_after.bin`
- `return_expected.bin`
- `len.bin`

Le replay recharge ces fichiers, execute a nouveau `compute()`, puis compare :

- la valeur de retour ;
- le contenu de `output` ;
- la valeur finale de `g_counter`.

## Exemple pour analyser une fonction Toto

> make show-report FUNC=toto OUT=/tmp/c_trace_replay_toto

## Cas a tester pour la tache 11

Les fichiers `examples/rw_cases.c` et `examples/rw_cases.h` servent de matrice
de validation pour l'analyse lecture/ecriture basee sur l'AST C.

Commande type :

```bash
make show-report SRC=examples/rw_cases.c HDR=examples/rw_cases.h FUNC=rw_array_read_write OUT=/tmp/rw_cases
```

Lancer toute la batterie :

```bash
make test-rw-cases
```

Les rapports sont generes dans `generated/rw_cases/`.

| Fonction | Forme C testee | Attendu |
| --- | --- | --- |
| `rw_array_read_write` | `output[i] = input[i]` | `input` lu, `output` ecrit |
| `rw_array_compound` | `buffer[i] += 1` | `buffer` lu et ecrit |
| `rw_array_increment` | `buffer[i]++` | `buffer` lu et ecrit |
| `rw_pointer_read` | `return *src` | `src` lu par dereferencement |
| `rw_pointer_write` | `*dst = 42` | `dst` ecrit par dereferencement |
| `rw_pointer_inout` | `*value += 1` | `value` lu et ecrit |
| `rw_struct_field_read` | `*dst = ctx->value` | `ctx->value` lu, `dst` ecrit |
| `rw_struct_field_write` | `ctx->value = value` | `ctx->value` ecrit |
| `rw_struct_field_inout` | `ctx->count += 1` | `ctx->count` lu et ecrit |
| `rw_struct_array_read` | `output[i] = ctx->table[i % 16]` | `ctx->table` lu, `output` ecrit |
| `rw_global_read` | `*dst = g_rw_mode` | `g_rw_mode` lu, `dst` ecrit |
| `rw_global_write` | `g_rw_counter = value` | `g_rw_counter` ecrit |
| `rw_global_inout` | `g_rw_counter++` | `g_rw_counter` lu et ecrit |
| `rw_call_with_pointer` | `mutate_buffer(buffer, len)` | appel detecte, effet sur `buffer` ambigu sans analyse du callee |
| `rw_conditional_read` | lecture dans un `if` | `input` lu, `output` ecrit |
| `rw_dynamic_index` | `input[i + offset]` | `input` lu avec plage dynamique, `output` ecrit |
| `rw_content_dependent_loop` | boucle `while (*src)` | `src` lu, `dst` ecrit, taille dependante du contenu |

## TODO

Les trois premieres taches de generalisation sont terminees cote analyse et
nommage des rapports. Le workflow capture/replay complet reste encore specialise
pour `compute()` tant que la generation du harness n'utilise pas vraiment
`report["function"]` et `report["parameters"]`.

| Numero | Priorite | Tache | Objectif | Etat |
| --- | --- | --- | --- | --- |
| 1 | Haute | Parametrer la fonction cible dans le `Makefile` | Permettre de choisir `FUNC`, `SRC`, `HDR` et `OUT` depuis la ligne de commande. | Fait |
| 2 | Haute | Generer les rapports avec le nom de la fonction | Produire par exemple `generated/<fonction>_report.json` au lieu de toujours ecrire `compute_report.json`. | Fait |
| 3 | Haute | Supprimer l'hypothese de retour `int` dans `tools/analyze.py` | Analyser aussi des fonctions `void`, `float`, `uint32_t`, pointeurs, structs, etc. | Fait |
| 4 | Haute | Utiliser `report["function"]` dans `tools/generate_harness.py` | Eviter que le harness genere appelle toujours `compute()`. | A faire |
| 5 | Haute | Generer les arguments du harness depuis `report["parameters"]` | Construire l'appel de la fonction cible a partir de sa signature reelle. | A faire |
| 6 | Haute | Decrire les donnees d'entree dans un format externe | Remplacer les valeurs codees en dur (`Context`, `input`, `len`) par un cas de test ou des annotations. | A faire |
| 7 | Moyenne | Rendre les noms des fichiers captures generiques | Eviter les noms specialises comme `ctx_before.bin` ou `output_expected.bin`. | A faire |
| 8 | Moyenne | Generaliser la comparaison de replay | Comparer automatiquement les sorties et globaux ecrits d'apres le `write_set`. | A faire |
| 9 | Moyenne | Ajouter une dependance Python `clang` | Preparer la migration vers une analyse AST C. | Fait |
| 10 | Moyenne | Recrire `tools/analyze.py` avec libclang | Remplacer les regex par un vrai parcours d'AST C. | En cours |
| 11 | Moyenne | Ajouter une analyse lecture/ecriture basee sur le contexte AST | Distinguer correctement lectures, ecritures et operations `inout`. | En cours |
| 12 | Moyenne | Signaler les appels non analyses comme ambigus | Produire des warnings ou annotations lorsqu'un pointeur est passe a une fonction non analysee. | A faire |
| 13 | Basse | Ajouter des exemples C plus varies | Tester pointeurs, structs imbriquees, retours non-`int`, macros, appels indirects et buffers dynamiques. | A faire |
| 14 | Basse | Ajouter des tests automatises sur les rapports JSON | Verifier que l'analyse produit les `read_set` / `write_set` attendus. | A faire |
