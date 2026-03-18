"""
AI Council v2 — Configuration centrale.

Règle fondamentale (SPECS §2) : aucun nom de modèle n'est codé en dur
dans la logique métier. Tout changement de modèle = changer une ligne ici.
"""

# ── Modèles des 6 agents ─────────────────────────────────────────────────────
# Format OpenRouter : "provider/model-name"
# Slot 3 (News) utilise xAI directement — la valeur ici sert de fallback label.

COUNCIL_CONFIG: dict[str, str] = {
    "slot_1_fundamentalist": "anthropic/claude-sonnet-4-5",
    "slot_2_quant":          "mistralai/magistral-medium",
    "slot_3_news":           "x-ai/grok-3",          # via xAI API (pas OpenRouter)
    "slot_4_contrarian":     "openai/gpt-4o",
    "slot_5_finance":        "mistralai/mistral-large-latest",
    "master":                "anthropic/claude-opus-4",
}

# Modèles de fallback gratuits (SPECS §6.1 + §9.1)
COUNCIL_FALLBACK_CONFIG: dict[str, str] = {
    "slot_1_fundamentalist": "meta-llama/llama-3.3-70b-instruct",
    "slot_2_quant":          "mistralai/magistral-medium",  # déjà ~gratuit
    "slot_3_news":           "meta-llama/llama-3.3-70b-instruct",
    "slot_4_contrarian":     "qwen/qwen3-235b-a22b",
    "slot_5_finance":        "mistralai/mistral-large-latest",  # déjà gratuit
    "master":                "meta-llama/llama-3.3-70b-instruct",
}

# Noms lisibles pour les logs / DB
AGENT_NAMES: dict[str, str] = {
    "slot_1_fundamentalist": "Fundamentalist",
    "slot_2_quant":          "Quant",
    "slot_3_news":           "News",
    "slot_4_contrarian":     "Contrarian",
    "slot_5_finance":        "Finance",
    "master":                "Master",
}

# ── URLs des providers ────────────────────────────────────────────────────────
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1/chat/completions"
XAI_BASE_URL: str        = "https://api.x.ai/v1/chat/completions"

# ── Vote — règles de décision (SPECS §3.1) ───────────────────────────────────
VOTE_CONFIDENCE_MIN: int        = 65    # seuil pour trader sans Master (0-100)
VOTE_INFORMATION_SUFFICIENCY_MIN: int = 65  # seuil pour ne pas attendre (0-100)
VOTE_HOLD_MAX_MINUTES: int      = 30    # attente max si données insuffisantes

# ── SL / TP — ATR (SPECS §5.1) ───────────────────────────────────────────────
ATR_MULTIPLIER_SL: float  = 2.0   # SL = entrée - (ATR × 2)
ATR_MULTIPLIER_TP: float  = 3.0   # TP = entrée + (ATR × 3)
RISK_MAX_PER_TRADE: float = 0.02  # 2% du capital par trade
RR_RATIO_MIN: float       = 1.5   # ratio risque/récompense minimum

# ── TTL des signaux (SPECS §5.3) — en minutes ────────────────────────────────
SIGNAL_TTL: dict[str, int] = {
    "NEWS_HIGH":  30,
    "BREAKOUT":   120,
    "MOMENTUM":   240,
    "FUNDAMENTAL": 1440,  # 24h
}

# ── Circuit Breaker (SPECS §6) ───────────────────────────────────────────────
CB_CONSECUTIVE_SL_TRIGGER: int   = 3      # 3 SL consécutifs → ORANGE
CB_MAX_LOSS_DAILY_PCT: float     = 0.05   # 5% de perte journalière → ORANGE
CB_MAX_LOSS_WEEKLY_PCT: float    = 0.10   # 10% de perte hebdomadaire → ROUGE
CB_VIX_YELLOW_THRESHOLD: float   = 25.0   # VIX > 25 → mode défensif (taille ÷ 2)
CB_VIX_RED_THRESHOLD: float      = 35.0   # VIX > 35 → BEAR_STRONG → pause trades
CB_INSUFFICIENCY_AGENTS_MIN: int = 3      # ≥ 3 agents insufficiency < 50 → JAUNE
CB_INSUFFICIENCY_SCORE_MIN: int  = 50     # seuil insufficiency pour trigger JAUNE

# ── Budget IA (SPECS §9) ─────────────────────────────────────────────────────
AI_BUDGET_MIN_EUR: float          = 5.0   # seuil survie OpenRouter
AI_BUDGET_ALERT_EUR: float        = 7.0   # alerte avant minimum
AI_REINVEST_RATE: float           = 0.02  # 2% des gains → pot IA
XAI_BUDGET_MIN_EUR: float         = 3.0   # seuil survie xAI

# Budgets fictifs initiaux pour permettre la compilation sans clés réelles
AI_BUDGET_INITIAL_EUR: float     = 10.0
XAI_BUDGET_INITIAL_EUR: float    = 5.0

# ── News aggregator (SPECS §7.2) ─────────────────────────────────────────────
NEWS_POLL_INTERVAL_SECONDS: int  = 300    # 5 min
MACRO_POLL_INTERVAL_SECONDS: int = 900    # 15 min
NEWS_IMPACT_HIGH_THRESHOLD: int  = 5      # score ≥ 5 → HIGH
NEWS_IMPACT_MEDIUM_THRESHOLD: int = 2     # score 2-4 → MEDIUM

NEWS_KEYWORDS_HIGH: list[str] = [
    "fed rate", "interest rate", "earnings beat", "earnings miss",
    "merger", "acquisition", "bankruptcy", "sec investigation",
    "crash", "recession", "inflation surge",
]

NEWS_KEYWORDS_MEDIUM: list[str] = [
    "guidance", "forecast", "analyst upgrade", "analyst downgrade",
    "layoffs", "ceo resign", "product launch", "partnership",
]

# ── Market Regime (SPECS §8) ─────────────────────────────────────────────────
MARKET_REGIME_CACHE_HOURS: int = 24   # recalculé à l'ouverture chaque jour

# Fenêtre de calcul des indicateurs macro
MARKET_REGIME_EMA200_PERIOD: int = 200
MARKET_REGIME_EMA50_PERIOD: int  = 50

# ── Pondération agents (SPECS §3.2) ──────────────────────────────────────────
AGENT_WEIGHT_DEFAULT: float  = 1.0
AGENT_WEIGHT_MIN: float      = 0.3
AGENT_WEIGHT_MAX: float      = 2.0
AGENT_STATS_LOOKBACK_DAYS: int = 30

# ── Phase paper trading — 4 configs en test parallèle (SPECS §12.2) ──────────
PAPER_CONFIGS: dict[str, dict] = {
    "A": {"sl_pct": 0.05, "tp_pct": 0.10, "risk_per_trade": 0.01, "method": "fixed"},
    "B": {"sl_pct": 0.08, "tp_pct": 0.15, "risk_per_trade": 0.02, "method": "fixed"},
    "C": {"sl_pct": 0.12, "tp_pct": 0.20, "risk_per_trade": 0.03, "method": "fixed"},
    "D": {"sl_atr": 2.0,  "tp_atr": 3.0,  "risk_per_trade": 0.02, "method": "atr"},
}

# Config paper active par défaut
ACTIVE_PAPER_CONFIG: str = "D"

# ── Timeouts API (ms) ────────────────────────────────────────────────────────
API_TIMEOUT_SECONDS: int         = 30
API_MAX_TOKENS_AGENT: int        = 1024
API_MAX_TOKENS_MASTER: int       = 2048
API_TEMPERATURE_AGENT: float     = 0.3
API_TEMPERATURE_MASTER: float    = 0.2
