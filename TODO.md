# TODO

| N | Etat | Tache | Description | Fichiers concernes |
|---|---|---|---|---|
| 1 | Fait | Filtrer les variables locales automatiques | Exclure des `read_set`, `write_set`, `inferred_captures` et `annotation_required` les acces bases sur des variables locales automatiques simples, par exemple `struct vecteur v; v.x = ...;`. Ces temporaires internes ne font pas partie de la frontiere observable du harness. | `tools/analyze.py` |
| 2 | Fait | Centraliser la notion de racine observable | Ajouter une fonction commune, par exemple `is_observable_root(symbol, report, local_symbols)`, pour decider si un acces doit etre conserve dans le rapport. | `tools/analyze.py` |
| 3 | Fait | Eviter les `no binding inferred` injustifies | Faire en sorte que `no binding inferred` n'apparaisse que pour un symbole reellement observable mais impossible a traduire automatiquement en expression C et en taille memoire. | `tools/generate_harness.py`, `tools/analyze.py` |
| 4 | Fait | Detecter les echappements d'adresse de variables locales | Ajouter des warnings lorsque l'adresse d'une variable locale automatique s'echappe, par exemple `helper(&v)`, `g_ptr = &v` ou `return &v`. | `tools/analyze.py` |
| 5 | Fait | Traiter separement les variables locales `static` | Detecter les variables `static` declarees dans une fonction. Les signaler comme etat persistant non capturable directement depuis un harness externe classique, sans generer de faux binding automatique. | `tools/analyze.py`, `tools/generate_harness.py` |
| 6 | Fait | Lister les variables internes decouvertes | Ajouter au rapport un champ structure, par exemple `locals`, listant les variables internes de la fonction avec leur nom, type, storage (`automatic`, `static`), location et statut d'observabilite. | `tools/analyze.py`, `README.md` |
| 7 | Fait | Ajouter des cas de test dedies | Ajouter des exemples couvrant les locales automatiques, les locales utilisees pour calculer une sortie, les echappements d'adresse, les locales `static`, la liste `locals` et les noms proches entre globale, parametre et locale. | `examples/rw_cases.c`, `examples/rw_cases.h`, `tools/test_reports.py` |
| 8 | Fait | Documenter la frontiere observable | Ajouter une section expliquant que le harness capture les frontieres observables de la fonction, pas ses temporaires internes. | `README.md` |

## Notes

Racines a conserver dans le rapport :

- parametres de la fonction ;
- memoire pointee par les parametres ;
- globales ;
- champs issus de parametres, par exemple `ctx->field` ;
- etats persistants explicitement detectes.

Racines a exclure du rapport :

- variables locales automatiques ;
- temporaires internes ;
- champs de variables locales automatiques, par exemple `v.x`.

Annotation possible pour une variable locale `static` :

```json
{
  "symbol": "acc",
  "reason": "function-local static state is not externally capturable without instrumentation"
}
```

Exemple de champ `locals` attendu :

```json
{
  "locals": [
    {
      "name": "v",
      "type": "struct vecteur",
      "storage": "automatic",
      "observable": false,
      "location": {
        "file": "examples/foo.c",
        "line": 12,
        "column": 20
      }
    }
  ]
}
```

## Trace longue par wrapper

| N | Etat | Tache | Description | Fichiers concernes |
|---|---|---|---|---|
| T1 | A faire | Ajouter un mode de generation `trace` | Permettre au generateur de produire un harness de trace longue en plus du mode actuel `single`, sans changer le fonctionnement existant. | `tools/generate_harness.py`, `Makefile` |
| T2 | A faire | Generer un wrapper d'appel | Produire une fonction `__ctrace_capture_<fonction>(...)` qui capture les entrees avant l'appel, appelle la vraie fonction, capture les sorties apres l'appel, puis retourne la valeur de retour. | `tools/generate_harness.py` |
| T3 | A faire | Ajouter un compteur d'appels | Ajouter un compteur persistant dans le wrapper afin d'associer chaque appel a un identifiant stable, par exemple `call_000001`, `call_000002`, etc. | `tools/generate_harness.py` |
| T4 | A faire | Stocker chaque appel dans un sous-dossier | Modifier les helpers de sauvegarde pour ecrire les captures dans `testcases/<fonction>_trace_001/call_<id>/` au lieu d'ecraser un seul cas. | `tools/generate_harness.py` |
| T5 | A faire | Generer un `manifest.json` de trace | Enregistrer la liste des appels captures, leur ordre et les metadonnees utiles afin que le replay puisse rejouer la sequence exacte. | `tools/generate_harness.py` |
| T6 | A faire | Generer un replay sequentiel | Produire un replay capable de lire le manifest, restaurer les entrees de chaque appel, appeler la fonction cible et comparer les sorties attendues dans l'ordre. | `tools/generate_harness.py` |
| T7 | A faire | Documenter le mode trace | Expliquer la difference entre capture unitaire, trace longue sequentielle et replay appel-par-appel independant. Preciser le role du wrapper. | `README.md` |
| T8 | A faire | Ajouter des cibles Makefile dediees | Ajouter des commandes separees pour generer, compiler et tester le mode trace sans modifier `make test`. | `Makefile` |
| T9 | A faire | Ajouter des tests de non-regression | Creer un scenario simple ou plusieurs appels successifs a une fonction sont captures puis rejoues dans le meme ordre. | `examples/`, `tools/test_reports.py`, tests harness |
| T10 | A faire | Clarifier les etats persistants | Definir le comportement attendu lorsque la fonction utilise des globales ou des variables locales `static`: replay sequentiel depuis un etat initial connu, ou instrumentation requise pour rejouer les appels independamment. | `README.md`, `tools/analyze.py`, `tools/generate_harness.py` |

Principe du wrapper :

```c
ret_type __ctrace_capture_F(args...)
{
    size_t call_id = __ctrace_next_call_id();
    __ctrace_capture_before_F(call_id, args...);
    ret_type ret = F(args...);
    __ctrace_capture_after_F(call_id, args..., ret);
    return ret;
}
```

Le wrapper ne remplace pas l'analyse de `F`. Il permet d'enregistrer une trace
longue en observant les appels reels de `F` pendant l'execution d'un programme.
