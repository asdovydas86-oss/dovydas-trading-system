# Financial Market Intelligence & Trading System
## Project Specification V1

**Version:** 1.0  
**Status:** Active foundation document  
**Purpose:** Define the vision, architecture, principles, priorities, and development path for the Financial Market Intelligence & Trading System.

---

## 1. Project Vision

The long-term goal is to build a modular AI-assisted financial market intelligence and trading system that helps the user:

- understand global financial markets;
- monitor crypto, stocks, indices, sectors, commodities, and macro conditions;
- research long-term investments;
- analyze swing-trading opportunities;
- later support day-trading research and controlled automation;
- combine technical, fundamental, macro, geopolitical, news, on-chain, derivatives, and portfolio information;
- improve decision quality rather than simply generate BUY or SELL signals;
- learn programming, AI systems, automation, market analysis, and quantitative thinking while building the system.

The system should evolve into a personal financial-market operating environment: one place where data is collected, analyzed, compared, scored, explained, tested, and eventually used for carefully controlled execution.

The system must remain modular. It should not become one large opaque AI agent that attempts to do everything at once.

---

## 2. Current Starting Point

The project is not starting from zero.

Existing work includes:

- a Swing Trading Analyzer prototype;
- TradingView MCP integration;
- Claude Code integration;
- multi-timeframe market analysis;
- previous strategy iterations, including v2 and v3 work;
- technical indicator analysis;
- Git-based development;
- experiments with AI-assisted market interpretation.

Existing work must be audited before major rewrites.

Useful components should be preserved, documented, tested, and improved. No existing code should be deleted or replaced simply because a new architecture is being designed.

---

## 3. Core Development Philosophy

### 3.1 Deterministic computation first

Whenever a value can be calculated objectively, code should calculate it.

Examples:

- EMA values and slopes;
- RSI values;
- MACD line, signal line, histogram, histogram momentum, and rate of change;
- ATR and volatility;
- volume ratios;
- distance from moving averages;
- swing highs and lows;
- support and resistance candidates;
- trend structure;
- risk/reward;
- position size;
- drawdown;
- portfolio exposure.

AI should not be asked to visually guess values that code can calculate precisely.

### 3.2 AI interpretation second

AI should be used where contextual reasoning adds value.

Examples:

- combining multiple signals;
- identifying conflicting evidence;
- interpreting market regime;
- comparing bullish and bearish scenarios;
- analyzing news mechanisms;
- connecting macro conditions with asset behavior;
- interpreting on-chain and derivatives data;
- explaining uncertainty;
- generating structured research summaries.

The preferred architecture is:

**Data → Deterministic calculations → Structured features → AI interpretation → Decision support**

### 3.3 No black-box dependency

The system should not depend on one AI model, one data provider, one broker, one exchange, or one MCP server.

External services should be treated as replaceable adapters.

TradingView MCP is useful, but it should not become the permanent core of the entire system.

---

## 4. Analytical Principles

### 4.1 Indicators are contextual, not binary

Indicators must never be interpreted using simplistic rules such as:

- MACD below zero = automatically bearish;
- RSI oversold = automatically buy;
- price below an EMA = automatically short;
- bullish crossover = automatically enter long.

The system must analyze:

- direction;
- momentum;
- acceleration or deceleration;
- slope;
- location relative to historical context;
- divergences;
- price structure;
- volume;
- volatility;
- timeframe alignment;
- market regime.

### 4.2 MACD interpretation

MACD is a major example of why contextual interpretation is required.

A MACD histogram can remain below zero while bearish momentum is weakening. A transition from strongly negative histogram bars toward smaller negative bars may represent improving momentum before a conventional bullish crossover occurs.

The system should calculate and distinguish:

- MACD line value;
- signal line value;
- histogram value;
- histogram direction;
- histogram rate of change;
- consecutive improvement or deterioration;
- bullish and bearish crossovers;
- distance between MACD and signal;
- zero-line position;
- bullish and bearish divergence;
- relationship with price structure.

A negative MACD value is not, by itself, sufficient evidence for a bearish conclusion.

### 4.3 EMA interpretation

EMA analysis should include:

- price above or below EMA;
- EMA slope;
- distance from EMA;
- reclaim or rejection;
- compression;
- dynamic support or resistance;
- relationship between multiple EMAs;
- higher-timeframe context.

Price below an EMA can be bearish, but it can also represent a potential recovery setup if momentum, structure, volume, and other evidence begin improving.

### 4.4 RSI interpretation

RSI should include:

- current level;
- direction;
- slope;
- recovery from extremes;
- failure swings where relevant;
- bullish and bearish divergence;
- timeframe context.

Oversold does not automatically mean buy, and overbought does not automatically mean sell.

### 4.5 Market structure and price action

Technical analysis should increasingly include deterministic structure detection:

- higher highs;
- higher lows;
- lower highs;
- lower lows;
- break of structure;
- change of character where rules can be defined;
- swing points;
- support and resistance;
- consolidation;
- breakout;
- retest;
- trend continuation;
- trend exhaustion.

Candlestick information may be used, but individual candle names should not dominate the analysis without context.

### 4.6 Avoid double-counting evidence

Correlated indicators must not be treated as fully independent confirmations.

For example:

- EMA trend;
- MACD trend;
- moving-average crossover;

may all partly represent the same underlying price momentum.

The system should group evidence into broader categories such as:

- trend;
- momentum;
- structure;
- volume;
- volatility;
- derivatives;
- on-chain;
- macro;
- news/catalysts.

Confidence should be based on diversity and quality of evidence, not simply the number of indicators pointing in one direction.

---

## 5. Multi-Timeframe Analysis

Different trading styles require different timeframe structures.

For swing trading, the initial framework should prioritize:

1. higher timeframe for primary regime and trend;
2. middle timeframe for setup development;
3. lower execution timeframe for entry timing.

A typical crypto swing workflow may use:

- 1W for structural context;
- 1D for primary setup;
- 4H for execution.

This is not a permanent universal rule. Timeframes should eventually be configurable by strategy.

The system must avoid mixing timeframe signals without explaining their role.

Example:

- Weekly: bullish structural trend.
- Daily: correction.
- 4H: early momentum reversal.

That combination is different from simply calling the asset “bullish.”

---

## 6. Decision Framework

The system should not produce only BUY, SELL, LONG, or SHORT.

A valid analysis may conclude:

- LONG candidate;
- SHORT candidate;
- WAIT;
- NO TRADE;
- WATCH FOR CONFIRMATION;
- INVALIDATED.

Each trade analysis should eventually include:

- market regime;
- higher-timeframe context;
- current setup;
- bullish evidence;
- bearish evidence;
- conflicting evidence;
- confirmation conditions;
- potential entry zone;
- invalidation;
- stop-loss logic;
- target logic;
- risk/reward;
- key risks;
- confidence level;
- missing data.

The system must explicitly separate:

**Observation → Interpretation → Scenario → Decision**

---

## 7. Bias Control

The system must actively guard against:

- confirmation bias;
- LONG bias;
- SHORT bias;
- recency bias;
- overfitting;
- hindsight bias;
- indicator double-counting;
- excessive confidence from incomplete data.

Before recommending a directional trade, the analysis should attempt to construct the strongest reasonable opposing case.

A LONG analysis should ask:

> What evidence would make this setup fail?

A SHORT analysis should ask the same from the opposite direction.

NO TRADE and WAIT are valid and often preferable outcomes.

---

## 8. Risk Management

Capital preservation is a core system requirement.

### 8.1 Per-trade risk

A maximum of 2% portfolio risk per trade is a hard ceiling, not a default target.

The system should support lower risk levels depending on:

- setup quality;
- volatility;
- liquidity;
- leverage;
- market regime;
- correlation with existing positions;
- event risk.

### 8.2 Portfolio-level risk

Risk must eventually be measured across the entire portfolio.

The system should consider:

- total open risk;
- correlated positions;
- sector concentration;
- crypto concentration;
- geographic concentration;
- leverage;
- drawdown;
- volatility;
- stablecoin exposure;
- exchange/custody exposure.

Five individually acceptable positions can still create excessive portfolio risk if they are highly correlated.

### 8.3 Leverage

Leverage does not create an edge.

It magnifies:

- profits;
- losses;
- liquidation risk;
- execution errors;
- model errors.

Automated systems must use explicit leverage limits and hard risk controls.

---

## 9. Long-Term Investment Module

Long-term investing must remain separate from short-term trading.

The investment module should analyze:

- business or protocol thesis;
- sector;
- market opportunity;
- competitive position;
- fundamentals;
- valuation where applicable;
- catalysts;
- risks;
- time horizon;
- portfolio role;
- position sizing;
- technical entry timing.

Target coverage may include:

- crypto infrastructure;
- Bitcoin and major crypto assets;
- AI;
- financial infrastructure;
- payments;
- stablecoins;
- tokenization;
- China and Hong Kong markets;
- US markets;
- emerging markets;
- mining companies;
- commodities;
- selected thematic sectors.

A technically weak chart does not automatically invalidate a strong long-term thesis, and a strong chart does not automatically create a good long-term investment.

---

## 10. Swing Trading Module

The Swing Trading Module is the first major trading-analysis priority.

Its responsibilities should eventually include:

- market scanning;
- multi-timeframe analysis;
- technical feature calculation;
- setup detection;
- candidate ranking;
- scenario generation;
- risk calculation;
- trade-plan generation;
- backtesting;
- paper-trade tracking;
- post-trade review.

The current Swing Trading Analyzer should be audited and evolved rather than blindly replaced.

---

## 11. Day Trading and Automation

Live automated day trading is not the current priority.

The development path must be:

**Research → Explicit rules → Historical backtesting → Robustness testing → Paper trading → Shadow mode → Small controlled live testing → Gradual scaling**

No strategy should move directly from an AI idea to live capital.

### 11.1 Shadow mode

Shadow mode means:

- the system receives live data;
- generates trades;
- records hypothetical entries and exits;
- does not execute real orders.

This allows comparison between expected and real-time behavior before risking capital.

### 11.2 Controlled live execution

If live execution is eventually enabled:

- API keys must not allow withdrawals;
- position-size limits must exist;
- leverage limits must exist;
- maximum daily loss must exist;
- maximum drawdown controls must exist;
- kill switches must exist;
- all orders and decisions must be logged;
- execution must be separable from analysis.

---

## 12. Market Intelligence Layer

The system should eventually provide a daily market-intelligence view.

It should cover:

- crypto;
- major stock indices;
- relevant equities;
- commodities;
- interest rates;
- currencies where relevant;
- macroeconomic events;
- geopolitical developments;
- market-moving news.

The purpose is not to summarize every headline.

For important events, the system should analyze:

1. What happened?
2. What is confirmed?
3. What is interpretation or speculation?
4. Through what mechanism could markets be affected?
5. Which assets or sectors are directly affected?
6. How did the market actually react?
7. Is the reaction consistent with the headline?
8. What second-order effects are possible?
9. What should be monitored next?

---

## 13. Crypto On-Chain Intelligence

On-chain data is a required future module, especially for crypto.

Potential categories include:

- exchange inflows and outflows;
- stablecoin supply and flows;
- large-holder behavior;
- realized profit/loss;
- MVRV-type valuation metrics;
- active addresses;
- network activity;
- transaction activity;
- protocol-specific metrics;
- token unlocks;
- treasury or foundation movements where relevant.

On-chain metrics must not be interpreted in isolation.

Example:

Large exchange inflows may suggest potential sell pressure, but the meaning depends on:

- the asset;
- the source of funds;
- market regime;
- derivatives positioning;
- actual subsequent price behavior.

---

## 14. Crypto Derivatives Intelligence

The derivatives module should eventually include:

- funding rates;
- open interest;
- liquidations;
- long/short positioning where reliable;
- basis;
- options data where available;
- volatility;
- positioning extremes.

The system should analyze combinations rather than single metrics.

Example:

Rising price + rapidly rising open interest + extreme positive funding may represent a different risk profile from rising price + moderate open interest + neutral funding.

---

## 15. Macro and Geopolitical Intelligence

The system should eventually track relevant macro variables such as:

- central-bank policy;
- interest rates;
- inflation;
- employment;
- liquidity;
- bond yields;
- US dollar conditions;
- major economic releases;
- fiscal policy;
- geopolitical conflicts;
- trade restrictions;
- sanctions;
- regulatory developments.

The system should explain transmission mechanisms rather than rely on slogans.

Example:

A geopolitical event may affect:

**event → energy supply risk → oil price → inflation expectations → bond yields → equity valuation pressure**

Not every event will follow the expected chain. Actual market reaction must be checked.

---

## 16. Data Architecture

The long-term architecture should separate:

### Data Sources

Examples:

- TradingView or TradingView MCP;
- exchange APIs;
- broker APIs;
- market-data providers;
- on-chain providers;
- derivatives providers;
- news sources;
- macroeconomic sources.

### Adapters

Each external provider should have a replaceable adapter.

### Normalized Data Layer

Different provider formats should be converted into consistent internal structures.

### Feature Engine

Calculates:

- indicators;
- structure;
- volatility;
- volume metrics;
- derivatives metrics;
- on-chain metrics;
- portfolio metrics.

### Analysis Engines

Potential engines:

- Technical Analysis Engine;
- On-Chain Engine;
- Derivatives Engine;
- Macro Engine;
- News Intelligence Engine;
- Fundamental Research Engine;
- Portfolio Risk Engine.

### Strategy Layer

Examples:

- Swing Strategy A;
- Swing Strategy B;
- future Day Strategy A;
- investment screening models.

### Decision Layer

Combines relevant evidence while avoiding duplicated signals.

### Execution Layer

Must remain isolated and disabled until explicitly tested and approved.

---

## 17. Proposed Modular Architecture

```text
financial-market-intelligence-system/
│
├── apps/
│   ├── dashboard/
│   └── cli/
│
├── src/
│   ├── data/
│   │   ├── providers/
│   │   ├── adapters/
│   │   └── normalization/
│   │
│   ├── features/
│   │   ├── technical/
│   │   ├── structure/
│   │   ├── volume/
│   │   ├── volatility/
│   │   ├── onchain/
│   │   └── derivatives/
│   │
│   ├── analysis/
│   │   ├── technical/
│   │   ├── macro/
│   │   ├── news/
│   │   ├── onchain/
│   │   └── portfolio/
│   │
│   ├── strategies/
│   │   ├── swing/
│   │   └── day/
│   │
│   ├── risk/
│   ├── backtesting/
│   ├── paper_trading/
│   ├── execution/
│   └── reporting/
│
├── tests/
├── docs/
├── config/
└── scripts/
```

This is a target architecture, not an instruction to immediately restructure the existing repository.

The live repository must first be audited.

---

## 18. Backtesting Principles

Backtests must be treated skeptically.

A strategy should not be judged only by total return.

Important metrics include:

- number of trades;
- win rate;
- average win;
- average loss;
- expectancy;
- profit factor;
- maximum drawdown;
- Sharpe or similar risk-adjusted metrics where appropriate;
- exposure;
- performance across different market regimes.

The system must guard against:

- overfitting;
- look-ahead bias;
- survivorship bias;
- data leakage;
- unrealistic fills;
- ignored fees;
- ignored slippage.

Strategies should be tested across:

- different assets;
- different periods;
- bull markets;
- bear markets;
- sideways markets;
- high-volatility periods;
- low-volatility periods.

---

## 19. AI Roles

### ChatGPT

Primary responsibilities:

- system architecture;
- project planning;
- research;
- market-analysis methodology;
- strategy design;
- review;
- documentation;
- explaining concepts;
- identifying risks and blind spots;
- helping coordinate development.

### Claude Code or another coding agent

Primary responsibilities:

- inspect the live repository;
- read actual files;
- implement approved changes;
- run tests;
- debug;
- refactor;
- update code documentation;
- create commits when appropriate.

Coding-agent output must be reviewed. No AI-generated code should be assumed correct merely because it runs.

---

## 20. Security

Never expose or commit:

- private keys;
- seed phrases;
- API secrets;
- authentication tokens;
- passwords.

Secrets should use:

- environment variables;
- local secret storage;
- `.env` files excluded by `.gitignore`;
- appropriate secret-management systems later.

Trading API keys should use minimum required permissions.

Automated trading systems must not have withdrawal permissions.

---

## 21. Documentation and Versioning

Important decisions should be documented.

Recommended core documents:

- `PROJECT_SPECIFICATION_V1.md`
- `ROADMAP.md`
- `DECISION_LOG.md`
- `ARCHITECTURE.md`
- strategy specifications;
- backtest reports;
- data-source documentation.

Major changes to the project vision should create new versions rather than silently overwriting history.

Examples:

- `PROJECT_SPECIFICATION_V1.md`
- `PROJECT_SPECIFICATION_V2.md`

Git should track code history.

Google Drive should store durable project documentation, research, reports, and important outputs.

---

## 22. Immediate Development Priority

The current priority is not live automated trading.

The initial development sequence is:

1. Establish the project documentation and working process.
2. Audit the existing live repository.
3. Map current files, components, integrations, and dependencies.
4. Identify useful code and technical debt.
5. Preserve working TradingView MCP functionality.
6. Identify subjective or fragile indicator interpretation.
7. Convert objective technical analysis into deterministic calculations.
8. Improve the Technical Analysis Engine.
9. Define explicit strategy rules.
10. Build tests and backtesting foundations.
11. Add data sources gradually.
12. Add on-chain and derivatives intelligence.
13. Add macro and news intelligence.
14. Build portfolio and risk intelligence.
15. Build paper trading.
16. Build shadow mode.
17. Only later evaluate controlled live execution.

Development should remain:

- modular;
- testable;
- understandable;
- documented;
- reversible;
- safe.

---

## 23. First Repository Audit Goals

Before major code changes, the repository audit should answer:

- What is the current folder structure?
- What languages and frameworks are used?
- What is the main application entry point?
- How does TradingView MCP work?
- What data is currently retrieved?
- How are indicators calculated?
- Which calculations are deterministic?
- Which conclusions are produced by AI?
- Where does LONG or SHORT bias enter?
- What changed between strategy versions?
- What tests exist?
- What is currently working?
- What is duplicated?
- What is obsolete?
- What is risky to modify?
- What should be preserved?

The output of the audit should become a separate document.

Suggested filename:

`CURRENT_SYSTEM_AUDIT_V1.md`

---

## 24. Long-Term Product Vision

The mature system may eventually provide:

### Daily Intelligence Brief

A concise overview of:

- overnight market moves;
- crypto conditions;
- stock-market conditions;
- macro developments;
- geopolitical developments;
- important news;
- on-chain changes;
- derivatives positioning;
- portfolio-relevant events;
- opportunities requiring attention.

### Opportunity Scanner

Ranks possible:

- long-term investments;
- swing trades;
- later short-term trades.

### Asset Research

Produces structured research for a selected:

- cryptocurrency;
- stock;
- sector;
- commodity;
- market.

### Portfolio Intelligence

Explains:

- exposure;
- concentration;
- correlations;
- risks;
- catalysts;
- upcoming events.

### Strategy Laboratory

Supports:

- rule design;
- backtesting;
- comparison;
- versioning;
- paper trading.

### Controlled Execution

Only after extensive validation, the system may support controlled automated execution with strict risk controls.

---

## 25. Success Criteria

The project is successful if it becomes more than an AI chatbot that gives market opinions.

The system should increasingly:

- use real structured data;
- calculate objective features;
- preserve analysis history;
- test strategies;
- measure performance;
- expose uncertainty;
- reduce emotional decision-making;
- help the user learn;
- improve over time through documented evidence.

The ultimate objective is not to predict every market move.

The objective is to build a disciplined decision-support system that improves the quality, consistency, transparency, and testability of financial-market decisions.

---

## 26. Working Rule

Build one reliable layer at a time.

**Small working module → Test → Review → Document → Commit → Next module**

Do not sacrifice robustness for speed, complexity, or impressive-looking AI output.
