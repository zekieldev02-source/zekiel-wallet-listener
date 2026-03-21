# zekiel-wallet-listener

Worker externe du projet Zekiel Trading Bot.

Écoute les transactions des wallets Solana suivis via Helius WebSocket,
détecte les achats exploitables et envoie des signaux au backend FastAPI.

## Architecture

```
Helius WebSocket (atlas endpoint)
  → wallet_event_parser   (normalisation du message brut)
  → signal_engine         (décision + construction du signal)
  → backend_client        (POST /internal/signals/buy)
```

Deux boucles asyncio concurrentes :
- **refresh_loop** : interroge `GET /internal/users/active` toutes les N secondes, synchronise les subscriptions Helius
- **listen_loop** : maintient la connexion WebSocket avec reconnexion automatique

## Prérequis

- Python 3.12+
- Compte Helius avec accès WebSocket (atlas endpoint)
- Backend `zekiel-trading-backend` démarré et accessible

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Remplir .env avec vos valeurs
```

## Configuration (.env)

| Variable | Description |
|---|---|
| `BACKEND_URL` | URL du backend FastAPI |
| `INTERNAL_API_KEY` | Clé partagée avec le backend (`X-Internal-API-Key`) |
| `HELIUS_WS_URL` | Endpoint WebSocket Helius (atlas) |
| `HELIUS_API_KEY` | Clé API Helius |
| `ACTIVE_USERS_REFRESH_SECONDS` | Fréquence de rafraîchissement des users actifs (défaut : 30) |
| `WS_RECONNECT_SECONDS` | Délai avant reconnexion WebSocket (défaut : 5) |
| `HTTP_TIMEOUT_SECONDS` | Timeout HTTP vers le backend (défaut : 5) |

## Lancement

```bash
python -m app.main
```

## Limitations MVP connues

- **entry_price** : calculé depuis les `tokenTransfers` Helius (SOL envoyé / tokens reçus). Approximatif — sera enrichi par `zekiel-market-stream` (Birdeye).
- **market_cap** : toujours `None` à ce stade — fourni par `zekiel-market-stream`.
- **token_symbol** : extrait si présent dans le message Helius, `None` sinon.
- La subscription Helius (`transactionSubscribe`) couvre les swaps confirmés. Pour une latence encore plus faible, migrer vers Helius LaserStream (gRPC) en remplaçant `HeliusWsClient`.

## Extension future : zekiel-market-stream

Ce repo émettra des signaux avec `entry_price` calculé localement et `market_cap=None`.
Le repo `zekiel-market-stream` (Birdeye) enrichira les données de prix en temps réel
et sera responsable de la fermeture des positions (exit strategy).
