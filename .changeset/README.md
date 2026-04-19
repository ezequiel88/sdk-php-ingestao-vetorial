# Changesets do SDK PHP

Cada PR que altere a API publica, o comportamento ou o empacotamento do SDK PHP deve incluir um arquivo em `.changeset/`.

Formato:

```md
---
php: patch
---

Resumo curto das mudancas que justificam o release.
```

Valores aceitos para `php`:

- `patch`
- `minor`
- `major`

Regras:

- Use apenas a chave `php` no front matter.
- Mudancas relevantes sem changeset falham no CI de pull request.
- Ao entrar na `main`, o workflow de release consome os changesets pendentes, cria um commit automatico removendo os arquivos consumidos e gera a tag `vX.Y.Z`.