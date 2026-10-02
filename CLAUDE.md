# CLAUDE.md — SDK PHP Ingestão Vetorial

Guia para agentes de IA trabalhando neste repositório.

## Visão geral

SDK cliente oficial em PHP para a API HTTP do projeto `ingestao-vetorial` (outro repositório do workspace). Foi extraído do monorepo `sdk-ingestao-vetorial` para um repositório dedicado, publicado no Packagist. Compatível com Laravel/Symfony. Veja o [CLAUDE.md da raiz do workspace](../CLAUDE.md) para o mapa completo entre projetos.

## Stack

- PHP 8.2+
- Guzzle 7 (HTTP client)
- PHPUnit 11 (testes), PHPStan 1.12 (análise estática)
- PSR-4 autoload: `IngestaoVetorial\` → `src/`, `IngestaoVetorial\Tests\` → `tests/`

## Estrutura

- `src/Client.php`: cliente principal (wrapping Guzzle, autenticação via API Key, DTOs de request/response)
- `tests/`: testes PHPUnit
- `.github/workflows/`: `ci.yml`, `release.yml`, `release-main.yml`, `packagist-sync.yml`

## Comandos de desenvolvimento

```bash
composer install
./vendor/bin/phpunit
./vendor/bin/phpstan analyse
```

## Convenções e gotchas

- Este pacote não deve crescer de volta para dentro do monorepo `sdk-ingestao-vetorial` — o PHP foi deliberadamente extraído para este repositório; não reintroduzir `sdk/php` lá.
- Publicação Composer/Packagist acontece exclusivamente a partir deste repositório (`packagist-sync.yml`).
- Mudança de URL pública/organização do GitHub exige atualizar `composer.json` (`homepage`, `support.source`, `support.issues`).

## Onde achar documentação mais profunda

- Uso do SDK, instalação, exemplos Laravel, referência de DTOs: [README.md](README.md)
- API consumida por este SDK: `ingestao-vetorial/docs/INTEGRACAO.md` (repositório irmão, fora deste repo)
