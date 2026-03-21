WSOL_MINT = "So11111111111111111111111111111111111111112"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Known DEX program IDs on Solana mainnet
RAYDIUM_AMM_V4 = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
ORCA_WHIRLPOOL = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
JUPITER_V6 = "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4"
PUMP_FUN = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

KNOWN_DEX_PROGRAMS: frozenset[str] = frozenset([
    RAYDIUM_AMM_V4,
    ORCA_WHIRLPOOL,
    JUPITER_V6,
    PUMP_FUN,
])

# Helius Enhanced event types treated as actionable buys
BUY_EVENT_TYPES: frozenset[str] = frozenset(["SWAP"])

SIGNAL_SOURCE = "helius-wallet-listener"
