# mao-Tool

Liste d'outils OSINT, avec site web pour chercher / filtrer / vérifier les liens.

Site : **https://schroder-mao.github.io/mao-Tool/**

## Fichiers

- `tools.json` — la liste (source)
- `maotool.md` — version markdown (générée)
- `status.json` — statut des liens (généré par `check_links.py`)
- `index.html` — le site
- `check_links.py` — vérifie les liens (clearnet + .onion via Tor)
- `build_md.py` — regénère `maotool.md` depuis `tools.json`

## Utilisation locale

```
python -m http.server 8000
```

Puis http://127.0.0.1:8000

## Ajouter un outil

Édite `tools.json`, puis :

```
python build_md.py
python check_links.py           # optionnel, met à jour status.json
```

## Licence

MIT
