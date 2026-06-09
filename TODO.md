# TODO

| N | Etat | Tache | Description | Fichiers concernes |
|---|---|---|---|---|
| 1 | A faire | Filtrer les variables locales automatiques | Exclure des `read_set`, `write_set`, `inferred_captures` et `annotation_required` les acces bases sur des variables locales automatiques simples, par exemple `struct vecteur v; v.x = ...;`. Ces temporaires internes ne font pas partie de la frontiere observable du harness. | `tools/analyze.py` |
| 2 | A faire | Centraliser la notion de racine observable | Ajouter une fonction commune, par exemple `is_observable_root(symbol, report, local_symbols)`, pour decider si un acces doit etre conserve dans le rapport. | `tools/analyze.py` |
| 3 | A faire | Eviter les `no binding inferred` injustifies | Faire en sorte que `no binding inferred` n'apparaisse que pour un symbole reellement observable mais impossible a traduire automatiquement en expression C et en taille memoire. | `tools/generate_harness.py`, `tools/analyze.py` |
| 4 | A faire | Detecter les echappements d'adresse de variables locales | Ajouter des warnings lorsque l'adresse d'une variable locale automatique s'echappe, par exemple `helper(&v)`, `g_ptr = &v` ou `return &v`. | `tools/analyze.py` |
| 5 | A faire | Traiter separement les variables locales `static` | Detecter les variables `static` declarees dans une fonction. Les signaler comme etat persistant non capturable directement depuis un harness externe classique, sans generer de faux binding automatique. | `tools/analyze.py`, `tools/generate_harness.py` |
| 6 | A faire | Ajouter des cas de test dedies | Ajouter des exemples couvrant les locales automatiques, les locales utilisees pour calculer une sortie, les echappements d'adresse, les locales `static` et les noms proches entre globale, parametre et locale. | `examples/rw_cases.c`, `examples/rw_cases.h`, `tools/test_reports.py` |
| 7 | A faire | Documenter la frontiere observable | Ajouter une section expliquant que le harness capture les frontieres observables de la fonction, pas ses temporaires internes. | `README.md` |

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
