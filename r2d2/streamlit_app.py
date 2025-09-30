# r2d2/streamlit_app.py
# --- garantir import do pacote r2d2 quando rodar via streamlit ---
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
# -----------------------------------------------------------------

import json
from datetime import date, datetime, timedelta
from copy import deepcopy
import pandas as pd
import numpy as np
import streamlit as st

from r2d2.config import CONFIG
from r2d2.strategy_manager import StrategyManager
from r2d2.backtester import Backtester
from r2d2.bybit_exchange import BybitCCXT
from r2d2.supabase_store import SupabaseStore
from r2d2.run_backtest import load_historical

st.set_page_config(page_title="R2D2 Backtester", layout="wide")
st.title("R2D2 Backtester – Nova Simulação, Otimização & Histórico")

# ========= HELPs (tooltips) =========
HELP = {
    # Gerais
    "symbol": (
        "O que é: Par/contrato que será testado, no formato CCXT da Bybit (perp USDT).\n"
        "Como funciona: Ex.: 'BTC/USDT:USDT', 'ACE/USDT:USDT'. O sufixo ':USDT' indica perp linear USDT.\n"
        "Por que alterar: Para testar outros ativos (blue chips ou memecoins) e comparar desempenho.\n"
        "Quando alterar: Sempre que quiser diversificar ou focar em moedas mais voláteis/liquidas."
    ),
    "timeframe": (
        "O que é: Intervalo de agregação dos candles (1m, 5m, 15m, 1h...).\n"
        "Como funciona: Estratégias de scalp tendem a usar 1–5m; swing, 15m–1h.\n"
        "Por que alterar: Afeta frequência de trades, ruído e custo relativo.\n"
        "Quando alterar: Se o ativo está muito ruidoso, suba o timeframe; se está parado, desça."
    ),
    "start": (
        "O que é: Data inicial do período de backtest.\n"
        "Como funciona: Baixa OHLCV a partir desta data (UTC).\n"
        "Por que alterar: Para testar cenários diferentes (tendência, consolidação) e evitar overfitting.\n"
        "Quando alterar: Ao validar a robustez em períodos variados."
    ),
    "end": (
        "O que é: Data final do período de backtest.\n"
        "Como funciona: Baixa OHLCV até esta data (UTC).\n"
        "Por que alterar: Para incluir ou excluir eventos específicos (alta/queda forte).\n"
        "Quando alterar: Ao comparar meses ou semanas diferentes."
    ),
    "initial": (
        "O que é: Capital inicial usado na simulação.\n"
        "Como funciona: Define a base para sizing/riscos (mesmo em simulação, influencia métricas percentuais).\n"
        "Por que alterar: Para ver impacto de alavancagem relativa e curva de equity.\n"
        "Quando alterar: Ao alinhar com o capital real que pretende usar."
    ),
    "commission": (
        "O que é: Taxa de negociação **por lado** (fração). Ex.: 0.0004 = 0,04% por lado.\n"
        "Como funciona: A simulação aplica taxa sobre **notional de entrada + saída**.\n"
        "Por que alterar: Exchanges/nível VIP diferem; maker < taker.\n"
        "Quando alterar: Se usar outra corretora/nível de taxas. Tip.: 0.0004–0.0006 é comum."
    ),
    "slippage": (
        "O que é: Slippage em **pontos de preço** por execução.\n"
        "Como funciona: Penaliza preço de entrada/saída para simular liquidez real.\n"
        "Por que alterar: Ativos finos/memecoins exigem slippage maior.\n"
        "Quando alterar: Se observar muita derrapagem real ou spreads maiores."
    ),
    "max_trades_day": (
        "O que é: Limite de trades por dia (RiskManager).\n"
        "Como funciona: Ao atingir o limite, novas entradas do dia são bloqueadas.\n"
        "Por que alterar: Controla overtrading e custos.\n"
        "Quando alterar: Em períodos de muita lateralização/ruído."
    ),
    "testnet": (
        "O que é: Usa ambiente de testes da Bybit para a **execução simulada**.\n"
        "Como funciona: Não afeta dados OHLCV (que são reais via CCXT), apenas o objeto de exchange.\n"
        "Por que alterar: Para separar ambiente de desenvolvimento/produção.\n"
        "Quando alterar: Mantenha ligado em simulações; desligue se for integrar com produção."
    ),
    "max_daily_loss": (
        "O que é: Perda máxima diária (USD). Ao atingir, o dia é encerrado.\n"
        "Como funciona: RiskManager checa PnL do dia e bloqueia novas entradas.\n"
        "Por que alterar: Para limitar drawdown e preservar capital.\n"
        "Quando alterar: Defina como % do capital (ex.: 2–3%) se quiser disciplina diária."
    ),
    "cooldown_bars": (
        "O que é: Pausa (em candles) após uma perda/fechamento.\n"
        "Como funciona: Bloqueia novas entradas por N barras.\n"
        "Por que alterar: Evita sequências de erros em mercados ruidosos.\n"
        "Quando alterar: Se notar perdas em sequência após SLs."
    ),
    "hours": (
        "O que é: Horas do dia (UTC) **permitidas para ENTRADAS**.\n"
        "Como funciona: A estratégia só abre trade se o candle estiver em uma dessas horas.\n"
        "Por que alterar: Alguns horários têm liquidez/fluxos melhores (descobertos no seu relatório).\n"
        "Quando alterar: Use horas positivas (ex.: 2,4,6,14,16,22) para ‘virar o jogo’."
    ),
    "weekdays": (
        "O que é: Dias da semana **permitidos para ENTRADAS**.\n"
        "Como funciona: Ex.: ['Tuesday','Thursday'] só permite ter/qui.\n"
        "Por que alterar: Alguns dias performam melhor/tem menos custo.\n"
        "Quando alterar: Após análise por dia (métricas por DOW)."
    ),

    # Estratégia
    "sl_atr_mult": (
        "O que é: Multiplicador do stop baseado na volatilidade (ex.: ATR).\n"
        "Como funciona: Distância do SL ≈ sl_atr_mult × (escala de pontos). *Nota:* versão atual usa simplificação em pontos.\n"
        "Por que alterar: SL curto protege menos e pode stopar cedo; SL longo tolera ruído porém arrisca mais.\n"
        "Quando alterar: Aumente em mercados voláteis; reduza em mercados ‘limpos’."
    ),
    "tp_r_mult": (
        "O que é: Alvo (TP) em múltiplos de R (risco). Ex.: 2.2 ⇒ 2,2× a distância do SL.\n"
        "Como funciona: Se SL = 10 pts, TP=22 pts.\n"
        "Por que alterar: Alvos maiores melhoram payoff, mas reduzem taxa de acerto.\n"
        "Quando alterar: Se muitas saídas por pouco lucro, teste aumentar; se raramente atinge TP, reduza."
    ),
    "bars_confirm_break": (
        "O que é: Nº de barras para **confirmar** rompimento/condição antes de entrar.\n"
        "Como funciona: Evita sinais ‘falsos’ exigindo X candles confirmando.\n"
        "Por que alterar: Mais confirmação = menos entradas, maior qualidade.\n"
        "Quando alterar: Em mercados com muitos falsos rompimentos, aumente."
    ),
    "min_atr_points": (
        "O que é: Volatilidade mínima (em pontos) para permitir operação.\n"
        "Como funciona: Bloqueia entradas quando o mercado está ‘morto’.\n"
        "Por que alterar: Reduz custo/ruído em períodos sem movimento.\n"
        "Quando alterar: Se ver muitas operações pequenas e sem edge."
    ),
    "filter_ema_slope": (
        "O que é: Filtro de direção do mercado pela inclinação da EMA.\n"
        "Como funciona: Exige uma inclinação mínima para operar apenas a favor do fluxo.\n"
        "Por que alterar: Operar contra a tendência tende a piorar resultados.\n"
        "Quando alterar: Mantenha ativo quando o mercado respeita tendências."
    ),
    "min_ema_slope_points": (
        "O que é: Inclinação mínima da EMA (em pontos) para considerar ‘tendência’.\n"
        "Como funciona: Se a inclinação for menor que o limite, bloqueia entradas.\n"
        "Por que alterar: Ajusta sensibilidade do filtro de tendência.\n"
        "Quando alterar: Suba em mercados voláteis; desça em mercados lentos."
    ),
    "use_break_even": (
        "O que é: Ativa mover o SL para o preço de entrada (Break-Even) após um ganho X em R.\n"
        "Como funciona: Ao atingir ‘break_even_r’, o stop sobe para 0 de prejuízo.\n"
        "Por que alterar: Protege lucro e reduz perdas após andar a favor.\n"
        "Quando alterar: Útil em ativos ariscos/memecoins."
    ),
    "break_even_r": (
        "O que é: Nível de lucro (em múltiplos de R) para acionar o Break-Even.\n"
        "Como funciona: Ex.: 1.0R move o SL para o preço de entrada ao ganhar 1R.\n"
        "Por que alterar: Mais cedo = mais proteção, mas pode ‘estopar no 0’ antes do alvo.\n"
        "Quando alterar: Ajuste conforme velocidade e ‘pullbacks’ do ativo."
    ),
    "use_atr_trailing": (
        "O que é: Ativa stop móvel (trailing) proporcional à volatilidade (ATR).\n"
        "Como funciona: O SL acompanha o preço conforme vai a favor, respeitando um múltiplo do ATR.\n"
        "Por que alterar: Captura tendências mais longas e protege lucro.\n"
        "Quando alterar: Útil em swings mais longos; pode reduzir WR em ranges."
    ),
    "trail_atr_mult": (
        "O que é: Multiplicador do ATR para a distância do trailing stop.\n"
        "Como funciona: Maior valor = stop mais folgado; menor = mais apertado.\n"
        "Por que alterar: Ajusta sensibilidade do trailing a ruído.\n"
        "Quando alterar: Suba em mercados ‘whipsaw’; desça em tendência limpa."
    ),

    # Sugestões/janelas
    "sugg_top_h": (
        "O que é: Quantas horas (por média de PnL) selecionar como ‘boas’.\n"
        "Como funciona: Rankeia horas por média de resultados, respeitando um mínimo de trades.\n"
        "Por que alterar: Controla agressividade do filtro temporal.\n"
        "Quando alterar: Em períodos em que poucas horas concentram o edge."
    ),
    "sugg_min_th": (
        "O que é: Mínimo de trades por hora para considerar na seleção.\n"
        "Como funciona: Evita escolher horas com amostra insuficiente.\n"
        "Por que alterar: Balanceia robustez vs. agressividade.\n"
        "Quando alterar: Suba se o período for longo e houver muitas trades."
    ),
    "sugg_top_d": (
        "O que é: Quantos dias da semana selecionar como ‘melhores’.\n"
        "Como funciona: Rankeia DOW por média de PnL com mínimo de trades.\n"
        "Por que alterar: Afina o corte por dia.\n"
        "Quando alterar: Se poucos dias concentram resultados positivos."
    ),
    "sugg_min_td": (
        "O que é: Mínimo de trades por dia para considerar na seleção.\n"
        "Como funciona: Evita viés por baixa amostra.\n"
        "Por que alterar: Aumente em períodos longos; reduza em curtos."
    ),

    # Otimização (grid)
    "grid_sl_list": (
        "O que é: Lista de valores para testar no SL ATR Mult (separe por vírgula).\n"
        "Como funciona: O grid roda todas as combinações de SL×TP×Trail.\n"
        "Por que alterar: Explorar espaço de parâmetros.\n"
        "Quando alterar: Para achar ‘ilhas’ de robustez, não apenas o máximo pontual."
    ),
    "grid_tp_list": (
        "O que é: Lista de valores para o TP em múltiplos de R.\n"
        "Como funciona: Combinado com SL e Trail no grid.\n"
        "Por que alterar: Ajustar payoff vs. taxa de acerto.\n"
        "Quando alterar: Ao buscar melhor PF/Expectancy."
    ),
    "grid_tr_list": (
        "O que é: Lista de valores para o Trail ATR Mult.\n"
        "Como funciona: Testa trailing mais justo/folgado.\n"
        "Por que alterar: Encontrar ajuste ao comportamento do ativo.\n"
        "Quando alterar: Em mercados com tendências longas ou ‘whipsaw’."
    ),
    "metric_target": (
        "O que é: Métrica para ordenar os resultados do grid.\n"
        "Como funciona: Rankeia por Net PnL, Profit Factor, Expectancy ou Win Rate.\n"
        "Por que alterar: Diferentes perfis (conservador vs. agressivo).\n"
        "Quando alterar: Para foco em PF (robustez) ou Net (retorno bruto)."
    ),
    "min_trades": (
        "O que é: Mínimo de trades para aceitar um resultado no grid.\n"
        "Como funciona: Filtra combinações com amostra pequena.\n"
        "Por que alterar: Evita overfitting.\n"
        "Quando alterar: Ajuste conforme o período e frequência da estratégia."
    ),
    "use_time_filters": (
        "O que é: Reutilizar as horas/dias do formulário na otimização.\n"
        "Como funciona: O grid roda já com esses filtros de entrada.\n"
        "Por que alterar: Se você já sabe janelas boas, acelera a busca.\n"
        "Quando alterar: Ao usar ‘horas vencedoras’ que você já descobriu."
    ),
    "run_suggest": (
        "O que é: Antes do grid, gera automaticamente horas/dias com base nos **últimos N dias**.\n"
        "Como funciona: Roda um baseline curto, rankeia horas/dias e aplica no grid.\n"
        "Por que alterar: Para adaptar às condições recentes.\n"
        "Quando alterar: Em mercados com regime que muda rápido."
    ),
    "suggest_days": (
        "O que é: Janela (em dias) para a sugestão automática de horas/dias.\n"
        "Como funciona: Considera apenas o fim do período (últimos N dias).\n"
        "Por que alterar: Ajusta quão ‘recente’ é a amostra.\n"
        "Quando alterar: Mercados quentes: janelas curtas (5–10d); estáveis: mais longas."
    ),
    "suggest_topH": (
        "O que é: Nº de melhores horas (por média) a aplicar no grid.\n"
        "Como funciona: Seleciona as top-N horas com mínimo de trades.\n"
        "Por que alterar: Balancear exploração vs. foco.\n"
        "Quando alterar: Ajuste conforme a dispersão de resultados entre horas."
    ),
    "suggest_minH": (
        "O que é: Mínimo de trades por hora para entrar no Top-Horas.\n"
        "Como funciona: Evita horas com amostra pequena.\n"
        "Por que alterar: Aumente em períodos longos; reduza em curtos."
    ),
    "suggest_topD": (
        "O que é: Nº de melhores dias da semana por média a aplicar no grid.\n"
        "Como funciona: Seleciona top-N dias com mínimo de trades.\n"
        "Por que alterar: Foco em dias com edge.\n"
        "Quando alterar: Se há concentração de resultados em poucos dias."
    ),
    "suggest_minD": (
        "O que é: Mínimo de trades por dia para entrar no Top-Dias.\n"
        "Como funciona: Evita dias com baixa amostra.\n"
        "Por que alterar: Ajuste conforme o total de trades do período."
    ),

    # Portfólio
    "min_vol": (
        "O que é: Volume 24h mínimo (USD) para considerar uma memecoin.\n"
        "Como funciona: Filtra mercados finos; quanto maior, mais liquidez.\n"
        "Por que alterar: Reduz slippage/spreads em ativos muito finos.\n"
        "Quando alterar: Se notar derrapagem alta, aumente o corte."
    ),
    "top_n": (
        "O que é: Quantidade de candidatos a listar (ordenados por volume).\n"
        "Como funciona: Limita a lista para escolhas manuais.\n"
        "Por que alterar: Foco em um universo gerenciável.\n"
        "Quando alterar: Mantenha entre 20–100, conforme sua necessidade."
    ),
    "portfolio_selected": (
        "O que é: Símbolos que vão compor o portfólio no backtest.\n"
        "Como funciona: Cada símbolo roda seu backtest e os PnLs são agregados.\n"
        "Por que alterar: Diversificar e comparar fontes de edge.\n"
        "Quando alterar: Sempre que quiser variar o universo."
    ),
}

# ========= Glossário & FAQ =========
# Cada item: term, cat, core (essencial?), desc (o que é), calc (como calcular), why (por que importa),
# when (quando ajustar/usar), tips (dicas)
GLOSSARY = [
    # ----- MÉTRICAS -----
    {"term":"Equity", "cat":"Métricas", "core":True,
     "desc":"Valor da conta **em tempo real** durante o backtest: capital inicial somado ao PnL acumulado das trades fechadas (nesta versão, PnL é realizado no fechamento).",
     "calc":"equity_t = equity_0 + Σ(pnl_i) até o tempo t",
     "why":"Mostra a **curva** do resultado; é a base para avaliar drawdown e estabilidade.",
     "when":"Sempre olhar ao comparar períodos/ativos/parametrizações.",
     "tips":"Curvas com **subidas regulares** e drawdowns curtos tendem a ser mais robustas."},

    {"term":"PnL (bruto e líquido)", "cat":"Métricas", "core":True,
     "desc":"Lucro/prejuízo por trade. **Bruto** antes de taxas/slippage; **Líquido** após taxas e slippage.",
     "calc":"pnl_líquido = pnl_bruto − fee − slippage_estimado",
     "why":"É o que realmente ‘vai para a equity’.",
     "when":"Use **líquido** para decisões; bruto serve só para entender o custo das fricções.",
     "tips":"Em alts/memecoins, **slippage** e spread podem ser relevantes."},

    {"term":"Win Rate (WR%)", "cat":"Métricas", "core":True,
     "desc":"% de trades vencedoras.",
     "calc":"WR% = (nº de pnl>0) / (nº total) × 100",
     "why":"Mede frequência de acerto; porém sem o payoff **não significa lucro**.",
     "when":"Útil em conjunto com **TP/SL** e **Expectancy**.",
     "tips":"Sistemas de tendência aceitam WR baixo se o **payoff** for alto."},

    {"term":"Profit Factor (PF)", "cat":"Métricas", "core":True,
     "desc":"Soma dos lucros dividida pela soma dos prejuízos (em valor absoluto).",
     "calc":"PF = Σ ganhos / |Σ perdas|",
     "why":"Robustez: PF>1 é lucrativo; **>1.3** já é bem razoável considerando fricções.",
     "when":"Comparar combinações/ativos.",
     "tips":"PF muito alto em poucos trades costuma ser **overfitting**."},

    {"term":"Expectancy (Ganho médio por trade)", "cat":"Métricas", "core":True,
     "desc":"Média do PnL por trade.",
     "calc":"Expectancy = Σ pnl / nº de trades",
     "why":"Diz o quanto você ganha em média cada vez que clica.",
     "when":"Ótimo para comparar **parametrizações** com número de trades diferente.",
     "tips":"Expectancy pequena pode evaporar com taxas altas."},

    {"term":"Max Drawdown (absoluto e %)", "cat":"Métricas", "core":True,
     "desc":"Queda máxima da equity desde um pico até um vale subsequente.",
     "calc":"MDD = min(equity − cummax(equity)); MDD% = MDD/peak",
     "why":"Controla ‘dor psicológica’ e risco de ruína.",
     "when":"Defina limites aceitáveis; ajuste risco/horários/SL.",
     "tips":"Combine com **max_daily_loss** e **cooldown** para ‘freio de mão’ diário."},

    {"term":"Recovery Factor", "cat":"Métricas",
     "desc":"Quanto o sistema gera de lucro por unidade de drawdown máximo.",
     "calc":"RecFactor = Net PnL / |MaxDD|",
     "why":"Avalia **qualidade** do retorno vs. sofrimento no caminho.",
     "when":"Comparar sistemas úteis para investidores avessos a drawdowns.",
     "tips":">1 é desejável; quanto maior, melhor."},

    {"term":"Sharpe / Sortino", "cat":"Métricas/Estatística",
     "desc":"Razões risco‑retorno: **Sharpe** usa desvio padrão total; **Sortino** penaliza só retornos negativos.",
     "calc":"Sharpe ≈ média(ret) / std(ret); Sortino ≈ média(ret) / std(negativos)",
     "why":"Capturam estabilidade do retorno.",
     "when":"Mais úteis em séries com sampling homogêneo (ex.: por dia).",
     "tips":"Cuidado com séries muito irregulares; prefira avaliar **PF + MDD** aqui."},

    # ----- RISCO / EXECUÇÃO -----
    {"term":"R (Risco por trade)", "cat":"Risco", "core":True,
     "desc":"Unidade de risco: distância até o stop em **pontos** multiplicada pelo tamanho (qty). TP/BE/Trail usam múltiplos de **R**.",
     "calc":"R = (|preço_entrada − preço_stop| em pontos) × qty × point_value",
     "why":"Padroniza metas (ex.: TP=2.2R).",
     "when":"Ajuste SL/TP olhando a **volatilidade** (ATR).",
     "tips":"Prefira comparar resultados em **R‑multiples** ao invés de apenas USDT."},

    {"term":"Position Sizing", "cat":"Risco", "core":True,
     "desc":"Tamanho da posição conforme risco desejado e stop.",
     "calc":"qty ≈ (risco_USD / (stop_em_pontos × point_value))",
     "why":"Mantém risco **constante** por trade.",
     "when":"Sempre; evita trades muito grandes em stops curtos.",
     "tips":"Cheque **contractSize/tickSize** do mercado para não violar mínimos."},

    {"term":"Max trades/dia", "cat":"Risco", "core":True,
     "desc":"Tampa a quantidade de operações por dia.",
     "calc":"Parâmetro do RiskManager.",
     "why":"Evita overtrading/custos em mercado ruim.",
     "when":"Se notar dias com 1000 cliques e pouco retorno.",
     "tips":"Combine com **cooldown** após perdas."},

    {"term":"Perda diária máxima", "cat":"Risco",
     "desc":"Limite de perda em USDT no dia; aciona trava.",
     "calc":"RiskManager encerra o dia se equity_dia ≤ −limite.",
     "why":"Protege a conta de dias ruins.",
     "when":"2–3% do capital como regra de bolso.",
     "tips":"Ajuste ao seu perfil; melhor perder o dia que a conta."},

    {"term":"Cooldown", "cat":"Risco",
     "desc":"Pausa de N barras após perda/fechamento.",
     "calc":"Bloqueio de novas entradas por N candles.",
     "why":"Reduz sequências de erros.",
     "when":"Mercado ‘whipsaw’; perdas em sequência.",
     "tips":"Comece com 3‑10 barras e ajuste."},

    {"term":"Break‑even", "cat":"Execução/Risco", "core":True,
     "desc":"Mover o stop para o **preço de entrada** após atingir X×R de lucro.",
     "calc":"Se lucro_atual ≥ break_even_r × R ⇒ SL = entry_price",
     "why":"Protege o trade que já andou a favor.",
     "when":"Mercados de ‘puxa‑e‑solta’ (pullbacks frequentes).",
     "tips":"BE muito cedo pode ‘te tirar’ antes do alvo."},

    {"term":"Trailing Stop (ATR)", "cat":"Execução/Estratégia", "core":True,
     "desc":"Stop móvel que acompanha o preço usando múltiplos do ATR.",
     "calc":"SL_trail ≈ preço_atual − trail_atr_mult × ATR (para longs)",
     "why":"Captura tendências mais longas.",
     "when":"Mercados tendenciais; evite trail muito apertado em whipsaw.",
     "tips":"Teste 0.5–1.5 como ponto de partida."},

    {"term":"Comissão (fee)", "cat":"Execução", "core":True,
     "desc":"Taxa cobrada por lado (maker/taker).",
     "calc":"fee ≈ taxa × notional (entrada + saída).",
     "why":"Impacto grande em alta frequência.",
     "when":"Atualize conforme seu nível VIP/corretora.",
     "tips":"Use taxa **por lado** na simulação; é mais realista."},

    {"term":"Slippage", "cat":"Execução", "core":True,
     "desc":"Derrapagem entre o preço desejado e o executado.",
     "calc":"slippage ≈ (preço_exec − preço_ref) em pontos × qty × point_value",
     "why":"Aumenta custo e reduz lucro.",
     "when":"Altas finas; horários vazios; ordens grandes.",
     "tips":"Aumente o parâmetro em memecoins/baixa liquidez."},

    {"term":"Spread / Tick / Point / Tick Size", "cat":"Execução/Mercado",
     "desc":"**Spread** é a diferença bid‑ask. **Tick** é o incremento mínimo de preço. ‘Point’ no código equivale a ‘ponto de preço’. **Tick Size** é o tamanho do passo do tick.",
     "calc":"spread = ask − bid; ex.: tick_size=0.1.",
     "why":"Afeta execução e custo.",
     "when":"Quanto menor o tick/spread, menor fricção.",
     "tips":"Respeite múltiplos de tick ao simular preços."},

    {"term":"Contract Size / Point Value / Notional", "cat":"Execução/Mercado",
     "desc":"**Contract Size**: tamanho por contrato. **Point Value**: valor monetário por ponto. **Notional**: tamanho total em USDT da posição.",
     "calc":"notional ≈ preço × qty × contractSize",
     "why":"Base para sizing e taxas.",
     "when":"Precisa estar correto por símbolo.",
     "tips":"Leia da exchange (CCXT) para cada perp."},

    {"term":"Alavancagem / Margem (initial/maintenance)", "cat":"Risco/Mercado",
     "desc":"Alavancagem multiplica exposição; margem é o colateral exigido.",
     "calc":"exposição = preço × qty; margem ≈ exposição / alavanc.",
     "why":"Risco de liquidação se equity < manutenção.",
     "when":"Use com parcimônia; não muda o edge.",
     "tips":"Gerencie risco via **sizing** e **SL**."},

    # ----- ESTRATÉGIA / INDICADORES -----
    {"term":"ATR (Average True Range)", "cat":"Estratégia/Mercado", "core":True,
     "desc":"Medida de **volatilidade**. Usamos para dimensionar SL/Trail.",
     "calc":"ATR = média móvel do True Range.",
     "why":"Adaptar stops ao ‘tamanho do giro’ do ativo.",
     "when":"Mercados voláteis: aumente SL/trail.",
     "tips":"No app, ‘Min ATR Points’ evita operar mercado ‘morto’."},

    {"term":"EMA (Média Móvel Exponencial) & Slope", "cat":"Estratégia", "core":True,
     "desc":"EMA foca nos preços recentes. **Slope** (inclinação) indica direção/força.",
     "calc":"slope ≈ variação da EMA por barra (em pontos).",
     "why":"Filtrar entradas contra a maré.",
     "when":"Ative ‘Filter EMA Slope’ e ajuste ‘Min EMA Slope Pts’.",
     "tips":"Slope mínimo alto = menos trades, melhor qualidade."},

    {"term":"Breakout & Bars Confirm Break", "cat":"Estratégia", "core":True,
     "desc":"Entrada por rompimento confirmada por X barras.",
     "calc":"Somente entra se o rompimento persistir por N barras.",
     "why":"Reduz falsos sinais.",
     "when":"Mercados com ‘fakeouts’.",
     "tips":"N muito alto pode reduzir demais a frequência."},

    {"term":"Stop Loss / Take Profit", "cat":"Estratégia/Risco", "core":True,
     "desc":"SL limita perda; TP realiza lucro no alvo (em múltiplos de R).",
     "calc":"SL ≈ sl_atr_mult × (escala de pontos); TP ≈ tp_r_mult × R.",
     "why":"Define payoff do sistema.",
     "when":"Ajuste conforme ATR/ruído.",
     "tips":"SL longuíssimo piora risco de ruína; TP minúsculo aumenta custo relativo."},

    # ----- DADOS / BACKTEST -----
    {"term":"Overfitting", "cat":"Dados/Backtest", "core":True,
     "desc":"Ajustar parâmetros ao **ruído** histórico (memorizar o passado).",
     "calc":"—",
     "why":"Resultados não se repetem no futuro.",
     "when":"Se PF ‘perfeito’ em poucos trades.",
     "tips":"Use **out-of-sample** e períodos diferentes."},

    {"term":"Data Snooping / p‑hacking", "cat":"Dados/Backtest",
     "desc":"Tentar muitas combinações e escolher a que ‘deu bom’ por acaso.",
     "calc":"—",
     "why":"Falso positivo estatístico.",
     "when":"Grids enormes sem validação externa.",
     "tips":"Prefira **ilhas de robustez** e valide fora da amostra."},

    {"term":"Look‑ahead bias", "cat":"Dados/Backtest", "core":True,
     "desc":"Usar informação que **não existia** no momento da decisão.",
     "calc":"—",
     "why":"Inviabiliza a simulação.",
     "when":"Indicadores que usam o fechamento futuro; ou latências ignoradas.",
     "tips":"Sempre calcule com dados **até a barra atual** apenas."},

    {"term":"Survivorship bias", "cat":"Dados/Backtest",
     "desc":"Considerar apenas ativos ‘sobreviventes’ e ignorar os que morreram.",
     "calc":"—",
     "why":"Superestima performance.",
     "when":"Listas de ativos atuais vs. passado.",
     "tips":"Considere universo **histórico** ao analisar longos períodos."},

    {"term":"In‑sample / Out‑of‑sample", "cat":"Dados/Backtest", "core":True,
     "desc":"Conjunto de calibração (**in‑sample**) vs. validação (**out‑of‑sample**).",
     "calc":"—",
     "why":"Evita ajuste ao ruído.",
     "when":"Sempre que otimizar parâmetros.",
     "tips":"Use o **walk‑forward** para rotina contínua."},

    {"term":"Walk‑forward", "cat":"Dados/Backtest",
     "desc":"Otimiza em janela A, valida em janela B; avança as janelas e repete.",
     "calc":"—",
     "why":"Validação de processo contínuo.",
     "when":"Operação sistemática no tempo.",
     "tips":"Ótimo para regimes que mudam."},

    {"term":"Grid Search / Otimização", "cat":"Dados/Backtest",
     "desc":"Avalia combinações discretas de parâmetros.",
     "calc":"—",
     "why":"Explorar espaço de configurações.",
     "when":"Sempre que houver SL/TP/Trail, etc.",
     "tips":"Evite grids gigantes; prefira ‘mini‑sweeps’ guiados por métricas."},

    # ----- MERCADO / PORTFÓLIO -----
    {"term":"Liquidez", "cat":"Mercado", "core":True,
     "desc":"Facilidade de negociar sem mover o preço.",
     "calc":"Proxy: volume 24h, profundidade do book, spread.",
     "why":"Afeta slippage e custos.",
     "when":"Memecoins finas podem enganar no backtest.",
     "tips":"Use corte por volume (24h) e slippage maior."},

    {"term":"Volatilidade", "cat":"Mercado",
     "desc":"Amplitude de variação de preço; maior vol = mais risco e oportunidade.",
     "calc":"ATR, desvio padrão de retornos.",
     "why":"Dimensiona stops e sizing.",
     "when":"Períodos mais voláteis pedem SL maior / risk menor.",
     "tips":"Combine **min_atr_points** com trails."},

    {"term":"Correlação", "cat":"Portfólio",
     "desc":"Grau de co‑movimento entre ativos.",
     "calc":"Correlação de retornos (ex.: diária).",
     "why":"Diversificação real reduz risco.",
     "when":"Evite portfólio de memecoins altamente correlacionadas.",
     "tips":"Selecione ativos com drivers diferentes."},

    {"term":"Diversificação / Pesos", "cat":"Portfólio",
     "desc":"Distribuir capital entre ativos. No app: peso **equal‑weight** por padrão.",
     "calc":"peso_i = 1/N (se não especificado).",
     "why":"Suaviza curva de equity.",
     "when":"Portfólios multi‑ativos.",
     "tips":"Futuro: **risk‑parity** (mesmo risco por ativo)."},

    {"term":"Rebalanceamento", "cat":"Portfólio",
     "desc":"Ajustar pesos periodicamente para voltar ao alvo.",
     "calc":"Mensal/semanal; regras.",
     "why":"Evita concentração excessiva.",
     "when":"Portfólios vivos.",
     "tips":"Cuidado com custos de transação."},
]

FAQ = [
    {"q":"Meu backtest tem poucas trades. O que olhar?",
     "a":"Verifique: (1) **allowed_hours/days** (pode estar muito restrito); (2) **min_atr_points** alto; "
          "(3) **bars_confirm_break** alto; (4) **filter_ema_slope** com **min_ema_slope_points** grande; "
          "(5) período curto/timeframe alto; (6) **max_trades_per_day** pequeno."},

    {"q":"Por que resultados idênticos no grid?",
     "a":"Certifique-se de passar **cfg.strat_params = sp** antes de criar o Backtester em cada combinação. "
          "No app atual isso já está corrigido."},

    {"q":"Como escolher SL/TP?",
     "a":"Use o **ATR** como régua de volatilidade: SL maior em mercados ruidosos; combine com **TP em R‑multiples** (ex.: 2.0–2.5R). "
          "Teste **Break‑even** entre 0.8–1.2R e **Trail ATR** entre 0.5–1.5."},

    {"q":"Qual slippage usar?",
     "a":"Blue‑chips (BTC/ETH): baixo (1–2 pontos). Memecoins/horários vazios: suba (3–10+). Olhe spreads médios."},

    {"q":"O que é overfitting e como evitar?",
     "a":"É ajustar ao ruído histórico. Evite com **out‑of‑sample**, **walk‑forward**, usar métricas robustas (PF, MDD), "
          "e evitando grids gigantes com escolha oportunista."},

    {"q":"Por que meu PnL no app é diferente do da corretora?",
     "a":"Diferenças de **taxa real, slippage, mínimos de contrato/tick**, horários e latência. "
          "Ajuste **commission_perc**, **slippage_points** e confirme **contractSize/tickSize** do símbolo."},
]

TRADE_FIELDS = [
    ("entry_time","Quando a posição foi aberta (UTC)."),
    ("exit_time","Quando a posição foi fechada (UTC)."),
    ("side","LONG ou SHORT."),
    ("entry_price","Preço de entrada."),
    ("exit_price","Preço de saída."),
    ("qty","Quantidade (em contratos/unidades)."),
    ("fee","Taxas pagas (entrada + saída)."),
    ("pnl","Lucro/Prejuízo líquido da trade."),
    ("equity","Equity após a trade."),
    ("close_reason","Motivo do fechamento (stop/exit/end)."),
    ("stop_kind","Se foi stop: 'tp' (alvo) ou 'sl' (stop loss)."),
    ("symbol","(Portfólio) qual ativo corresponde."),
]

def _filter_glossary(glossary, query, cats, core_only=False):
    q = (query or "").strip().lower()
    out = []
    for item in glossary:
        if cats and item["cat"] not in cats:
            continue
        if core_only and not item.get("core", False):
            continue
        hay = " ".join([
            item["term"], item["cat"],
            item.get("desc",""), item.get("calc",""),
            item.get("why",""), item.get("when",""), item.get("tips","")
        ]).lower()
        if q and q not in hay:
            continue
        out.append(item)
    return out

def _render_glossary(glossary):
    cats = sorted({x["cat"] for x in glossary})
    sel_cats = st.multiselect("Filtrar por categoria", cats, default=cats, key="help_cats")
    core_only = st.checkbox("Mostrar apenas termos essenciais", value=False, key="help_core_only")
    query = st.text_input("Buscar termo", value="", placeholder="Ex.: equity, overfitting, ATR…", key="help_search")
    filtered = _filter_glossary(glossary, query, sel_cats, core_only=core_only)

    if not filtered:
        st.info("Nada encontrado com os filtros atuais.")
        return

    # Agrupa por categoria
    for cat in sel_cats:
        group = [x for x in filtered if x["cat"] == cat]
        if not group: 
            continue
        st.markdown(f"### {cat}")
        for item in group:
            label = item["term"] + (" ⭐" if item.get("core") else "")
            with st.expander(label, expanded=False):
                st.markdown(f"**O que é:** {item.get('desc','—')}")
                if item.get("calc"):
                    st.markdown("**Como calcular / modelagem:**")
                    st.code(item["calc"])
                if item.get("why"):
                    st.markdown(f"**Por que importa:** {item['why']}")
                if item.get("when"):
                    st.markdown(f"**Quando usar/ajustar:** {item['when']}")
                if item.get("tips"):
                    st.markdown(f"**Dicas:** {item['tips']}")
        st.markdown("---")

def _params_help_dataframe():
    # Mapeia rótulos do app -> chaves do HELP
    mapping = [
        ("Symbol","symbol"),("Timeframe","timeframe"),("Data início","start"),("Data fim","end"),
        ("Capital inicial","initial"),("Commission (fração por lado)","commission"),("Slippage (pontos)","slippage"),
        ("Max trades/dia (RiskManager)","max_trades_day"),("Bybit Testnet","testnet"),
        ("Perda diária máxima","max_daily_loss"),("Cooldown (barras)","cooldown_bars"),
        ("Horas permitidas (UTC)","hours"),("Dias permitidos","weekdays"),
        ("SL ATR Mult","sl_atr_mult"),("TP R Mult","tp_r_mult"),("Bars Confirm Break","bars_confirm_break"),
        ("Min ATR Points","min_atr_points"),("Filter EMA Slope","filter_ema_slope"),
        ("Min EMA Slope Pts","min_ema_slope_points"),("Use BreakEven","use_break_even"),
        ("BreakEven R","break_even_r"),("Use ATR Trailing","use_atr_trailing"),("Trail ATR Mult","trail_atr_mult"),
        # Otimização
        ("SL ATR Mult (lista)","grid_sl_list"),("TP R Mult (lista)","grid_tp_list"),("Trail ATR Mult (lista)","grid_tr_list"),
        ("Métrica de ranking","metric_target"),("Mínimo de trades","min_trades"),
        ("Usar filtros de tempo da aba Rodar","use_time_filters"),
        ("🎯 Gerar sugestão antes do grid","run_suggest"),
        ("Sugestão: últimos N dias","suggest_days"),("Sugestão: top N horas","suggest_topH"),
        ("Sugestão: mín. trades/hora","suggest_minH"),("Sugestão: top N dias","suggest_topD"),
        ("Sugestão: mín. trades/dia","suggest_minD"),
        # Portfólio
        ("Volume 24h mínimo (USD)","min_vol"),("Top N por volume","top_n"),
        ("Símbolos selecionados (portfólio)","portfolio_selected"),
    ]
    rows = []
    for label, key in mapping:
        if key in HELP:
            rows.append({"Parâmetro": label, "Explicação": HELP[key]})
    return pd.DataFrame(rows)

def _render_trade_anatomy():
    st.markdown("### Anatomia de uma trade (colunas do CSV/DB)")
    df = pd.DataFrame(TRADE_FIELDS, columns=["Campo","Significado"])
    st.dataframe(df, use_container_width=True, hide_index=True)

def _render_faq():
    st.markdown("### FAQ")
    for i, qa in enumerate(FAQ, start=1):
        with st.expander(f"{i}. {qa['q']}"):
            st.markdown(qa["a"])


# ========= Helpers =========

@st.cache_data(show_spinner=False)
def get_bars_cached(symbol: str, timeframe: str, start: str, end: str):
    return load_historical(symbol=symbol, timeframe=timeframe, start_date=start, end_date=end)

def supabase_fetch_backtests(sb: SupabaseStore, symbol=None, timeframe=None, limit=100):
    try:
        if hasattr(sb, "list_backtests"):
            return sb.list_backtests(symbol=symbol, timeframe=timeframe, limit=limit)
        if hasattr(sb, "client"):
            q = sb.client.table("backtests").select("*").order("created_at", desc=True).limit(limit)
            if symbol: q = q.eq("symbol", symbol)
            if timeframe: q = q.eq("timeframe", timeframe)
            return q.execute().data
    except Exception as e:
        st.warning(f"Não foi possível buscar backtests no Supabase: {e}")
    return []

def supabase_fetch_trades(sb: SupabaseStore, backtest_id: int):
    try:
        if hasattr(sb, "get_trades"):
            return sb.get_trades(backtest_id) or []
        if hasattr(sb, "client"):
            q = sb.client.table("trades").select("*").eq("backtest_id", backtest_id).order("exit_time", desc=False)
            return q.execute().data
    except Exception as e:
        st.warning(f"Não foi possível buscar trades no Supabase: {e}")
    return []

def compute_metrics(df_trades: pd.DataFrame):
    if df_trades.empty:
        return {}
    pnl = pd.to_numeric(df_trades["pnl"], errors="coerce").fillna(0.0)
    equity = pd.to_numeric(df_trades.get("equity", pnl.cumsum()), errors="coerce").fillna(method="ffill").fillna(0.0)
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    pf = (wins / losses) if losses > 0 else np.nan
    wr = (pnl.gt(0).mean() * 100.0) if len(df_trades) else 0.0

    cummax = np.maximum.accumulate(equity)
    dd = equity - cummax
    max_dd = float(dd.min()) if len(dd) else 0.0
    idx_min = int(np.argmin(dd)) if len(dd) else 0
    peak = float(cummax[idx_min]) if len(cummax) else 0.0
    max_dd_pct = (max_dd / peak) if peak != 0 else np.nan

    return {
        "net_pnl": round(float(pnl.sum()), 4),
        "trades": int(len(df_trades)),
        "win_rate_%": round(float(wr), 2),
        "profit_factor": round(float(pf), 3) if not np.isnan(pf) else None,
        "expectancy": round(float(pnl.mean()), 5),
        "max_drawdown": round(max_dd, 4),
        "max_drawdown_%": round(float(max_dd_pct * 100), 2) if not np.isnan(max_dd_pct) else None,
    }

def show_metrics(metrics: dict, columns=6):
    if not metrics:
        st.info("Sem métricas para exibir.")
        return
    cols = st.columns(columns)
    for i, (k, v) in enumerate(metrics.items()):
        with cols[i % columns]:
            st.metric(k, v)

def parse_float_list(s: str) -> list:
    if not s: return []
    parts = [p.strip() for p in s.replace(";", ",").split(",")]
    out = []
    for p in parts:
        try: out.append(float(p))
        except: pass
    return out

# ======= Helpers de descoberta de universo (Bybit via CCXT) =======
import ccxt

BLUECHIPS = {"BTC","ETH","SOL","BNB","XRP","ADA","DOGE","TRX","DOT","LTC","BCH","MATIC","AVAX","LINK","ATOM","TON","NEAR","APT","OP","ARB","TIA"}
STABLES  = {"USDT","USDC","DAI","FDUSD","TUSD","PYUSD","FRAX"}

@st.cache_data(show_spinner=True, ttl=600)
def list_bybit_linear_usdt_perps_full() -> list[dict]:
    """
    Retorna info dos mercados perp lineares USDT na Bybit com tentativa de volume via fetch_tickers().
    """
    ex = ccxt.bybit()
    ex.set_sandbox_mode(False)
    ex.options["defaultType"] = "linear"
    markets = ex.load_markets()
    # tenta tickers; se falhar, segue sem volume
    try:
        tickers = ex.fetch_tickers()
    except Exception:
        tickers = {}
    out = []
    for m in markets.values():
        if m.get("type") == "swap" and m.get("linear") and m.get("quote") == "USDT":
            sym = m["symbol"]
            t = tickers.get(sym, {})
            last = t.get("last") or t.get("close")
            base_vol = t.get("baseVolume")
            quote_vol = t.get("quoteVolume")
            vol_usd = None
            if quote_vol is not None:
                vol_usd = float(quote_vol)
            elif base_vol is not None and last is not None:
                vol_usd = float(base_vol) * float(last)
            out.append({
                "symbol": sym,
                "base": m.get("base"),
                "quote": m.get("quote"),
                "active": m.get("active", True),
                "last": last,
                "vol24h_usd": vol_usd,
                "info": m,
            })
    # se não tiver volume, não ordene pelo volume
    if any(x.get("vol24h_usd") for x in out):
        out.sort(key=lambda d: (d["vol24h_usd"] is None, -(d["vol24h_usd"] or 0)), reverse=False)
    else:
        out.sort(key=lambda d: d["symbol"])
    return out

def is_probably_meme(base: str) -> bool:
    """Heurística simples: não-bluechip, não-stable, nome >=3 letras."""
    if not base: return False
    b = base.upper()
    if b in BLUECHIPS or b in STABLES:
        return False
    return len(b) >= 3

def filter_rank_memecoins(markets: list[dict], min_vol_usd: float = 1e6, top_n: int = 50) -> list[dict]:
    """Filtra e ranqueia 'memecoins' por heurística + volume 24h."""
    candidates = []
    for m in markets:
        if not m.get("active", True):
            continue
        base = m.get("base")
        if not is_probably_meme(base):
            continue
        v = m.get("vol24h_usd") or 0.0
        if v >= float(min_vol_usd):
            candidates.append(m)
    candidates.sort(key=lambda d: d.get("vol24h_usd", 0.0), reverse=True)
    return candidates[:int(top_n)]

@st.cache_data(show_spinner=True)
def get_bars_multi_cached(symbols: tuple[str, ...], timeframe: str, start: str, end: str):
    """Baixa OHLCV para vários símbolos (reutiliza seu load_historical)"""
    data = {}
    for s in symbols:
        data[s] = load_historical(symbol=s, timeframe=timeframe, start_date=start, end_date=end)
    return data

# ========= Layout =========
tab_run, tab_opt, tab_portfolio, tab_history, tab_help = st.tabs(
    ["▶️ Rodar Backtest", "🧪 Otimização (mini-sweep)", "💫 Portfólio (multi-ativos)", "📚 Histórico", "❓ Ajuda"]
)


# ========= TAB: Rodar Backtest =========
with tab_run:
    st.subheader("Parâmetros")
    with st.form("params_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1.2])
        with c1:
            symbol = st.text_input("Symbol", value=st.session_state.get("form_symbol","BTC/USDT:USDT"),
                                   key="form_symbol", help=HELP["symbol"])
        with c2:
            timeframe = st.selectbox("Timeframe", ["1m", "5m", "15m", "1h"], index=1,
                                     key="form_timeframe", help=HELP["timeframe"])
        with c3:
            start = st.date_input("Data início", value=st.session_state.get("form_start", date(2025, 9, 1)),
                                  key="form_start", help=HELP["start"])
        with c4:
            end = st.date_input("Data fim", value=st.session_state.get("form_end", date(2025, 9, 29)),
                                key="form_end", help=HELP["end"])

        c5, c6 = st.columns([1, 3])
        with c5:
            initial = st.number_input("Capital inicial",
                                      value=float(st.session_state.get("form_initial", 500.0)), step=50.0,
                                      key="form_initial", help=HELP["initial"])
            commission_perc = st.number_input("Commission (fração por lado)",
                                              value=float(st.session_state.get("form_commission", 0.0004)),
                                              step=0.0001, format="%.6f",
                                              key="form_commission", help=HELP["commission"])
            slippage_points = st.number_input("Slippage (pontos)",
                                              value=int(st.session_state.get("form_slippage", 2)), step=1,
                                              key="form_slippage", help=HELP["slippage"])
            max_trades_per_day = st.number_input("Max trades/dia (RiskManager)",
                                                 value=int(st.session_state.get("form_maxtrades", 200)), step=10,
                                                 key="form_maxtrades", help=HELP["max_trades_day"])
            testnet = st.checkbox("Bybit Testnet",
                                  value=bool(st.session_state.get("form_testnet", True)),
                                  key="form_testnet", help=HELP["testnet"])

            with st.expander("Opções de risco (se disponíveis)"):
                max_daily_loss = st.number_input("Perda diária máxima (USDT)",
                                                 value=float(st.session_state.get("form_maxdailyloss", 0.0)),
                                                 step=10.0, key="form_maxdailyloss", help=HELP["max_daily_loss"])
                cooldown_bars = st.number_input("Cooldown (barras)",
                                                value=int(st.session_state.get("form_cooldownbars", 0)),
                                                step=1, key="form_cooldownbars", help=HELP["cooldown_bars"])

            st.markdown("**Filtros de tempo para ENTRADAS**")
            default_hours = st.session_state.get("form_hours", [])
            hours = st.multiselect("Horas permitidas (UTC)", list(range(24)), default=default_hours,
                                   key="form_hours", help=HELP["hours"])
            default_weekdays = st.session_state.get("form_weekdays", [])
            weekdays = st.multiselect("Dias permitidos",
                                      ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
                                      default=default_weekdays, key="form_weekdays", help=HELP["weekdays"])

        with c6:
            st.markdown("**Parâmetros da estratégia**")
            pcols = st.columns(3)
            with pcols[0]:
                sl_atr_mult = st.number_input("SL ATR Mult",
                                              value=float(st.session_state.get("p_sl", 1.8)), step=0.1,
                                              key="p_sl", help=HELP["sl_atr_mult"])
                bars_confirm_break = st.number_input("Bars Confirm Break",
                                                     value=int(st.session_state.get("p_bcb", 1)), step=1,
                                                     key="p_bcb", help=HELP["bars_confirm_break"])
                use_break_even = st.checkbox("Use BreakEven",
                                             value=bool(st.session_state.get("p_be", True)),
                                             key="p_be", help=HELP["use_break_even"])
            with pcols[1]:
                tp_r_mult = st.number_input("TP R Mult",
                                            value=float(st.session_state.get("p_tp", 2.2)), step=0.1,
                                            key="p_tp", help=HELP["tp_r_mult"])
                min_atr_points = st.number_input("Min ATR Points",
                                                 value=int(st.session_state.get("p_minatr", 6)), step=1,
                                                 key="p_minatr", help=HELP["min_atr_points"])
                break_even_r = st.number_input("BreakEven R",
                                               value=float(st.session_state.get("p_ber", 1.0)), step=0.1,
                                               key="p_ber", help=HELP["break_even_r"])
            with pcols[2]:
                filter_ema_slope = st.checkbox("Filter EMA Slope",
                                               value=bool(st.session_state.get("p_ema", True)),
                                               key="p_ema", help=HELP["filter_ema_slope"])
                min_ema_slope_points = st.number_input("Min EMA Slope Pts",
                                                       value=int(st.session_state.get("p_emaslope", 3)), step=1,
                                                       key="p_emaslope", help=HELP["min_ema_slope_points"])
                use_atr_trailing = st.checkbox("Use ATR Trailing",
                                               value=bool(st.session_state.get("p_atrtrail", True)),
                                               key="p_atrtrail", help=HELP["use_atr_trailing"])
                trail_atr_mult = st.number_input("Trail ATR Mult",
                                                 value=float(st.session_state.get("p_trail", 0.5)), step=0.1,
                                                 key="p_trail", help=HELP["trail_atr_mult"])

        submitted = st.form_submit_button("🚀 Rodar Backtest", use_container_width=True)

    if submitted:
        # CONFIG geral
        CONFIG.initial_balance = float(initial)
        CONFIG.symbol = symbol
        CONFIG.timeframe = timeframe
        CONFIG.commission_perc = float(commission_perc)
        CONFIG.slippage_points = int(slippage_points)

        # Risk
        if hasattr(CONFIG, "risk"):
            if hasattr(CONFIG.risk, "max_trades_per_day"):
                CONFIG.risk.max_trades_per_day = int(max_trades_per_day)
            if hasattr(CONFIG.risk, "max_daily_loss"):
                CONFIG.risk.max_daily_loss = float(max_daily_loss)
            if hasattr(CONFIG.risk, "cooldown_bars"):
                CONFIG.risk.cooldown_bars = int(cooldown_bars)

        # Estratégia
        sp = CONFIG.strat_params
        sp.sl_atr_mult = float(sl_atr_mult)
        sp.tp_r_mult = float(tp_r_mult)
        sp.bars_confirm_break = int(bars_confirm_break)
        sp.min_atr_points = int(min_atr_points)
        sp.filter_ema_slope = bool(filter_ema_slope)
        sp.min_ema_slope_points = int(min_ema_slope_points)
        sp.use_break_even = bool(use_break_even)
        sp.break_even_r = float(break_even_r)
        sp.use_atr_trailing = bool(use_atr_trailing)
        sp.trail_atr_mult = float(trail_atr_mult)
        sp.allowed_hours = list(map(int, hours)) if hours else []
        sp.allowed_weekdays = list(map(str, weekdays)) if weekdays else []

        st.info(f"🔎 Baixando dados: {symbol}, {timeframe}, de {start} até {end}…")
        bars = get_bars_cached(symbol, timeframe, str(start), str(end))
        st.success(f"✅ Total de candles carregados: {len(bars)}")

        sm = StrategyManager(CONFIG.strategy, params=CONFIG.strat_params.__dict__)
        bt = Backtester(CONFIG, sm.get(), BybitCCXT(testnet=testnet))

        with st.spinner("Executando backtest..."):
            results = bt.run(bars)

        st.success("✅ Backtest concluído!")
        st.json(results)

        # Diagnóstico
        dbg = results.get("debug") if isinstance(results, dict) else None
        if not dbg:
            dbg = getattr(bt, "debug", None)
        if dbg:
            st.subheader("Diagnóstico de entradas/fechamentos")
            c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
            c1.metric("Sinais", dbg.get("signals", 0))
            c2.metric("Entradas", dbg.get("entries", 0))
            c3.metric("Bloq. Risk", dbg.get("blocked_risk", 0))
            c4.metric("Bloq. Tempo", dbg.get("blocked_time", 0))
            c5.metric("Stops", dbg.get("stop_closes", 0))
            c6.metric("Exits", dbg.get("exit_closes", 0))
            c7.metric("TP / SL", f"{dbg.get('tp_hits',0)} / {dbg.get('sl_hits',0)}")

            # Motivos de bloqueio
            reasons_dict = (dbg.get("blocked_reasons") or {}) if isinstance(dbg, dict) else {}
            if reasons_dict:
                reasons = pd.DataFrame([{"reason": k, "count": v} for k, v in reasons_dict.items()]) \
                            .sort_values("count", ascending=False)
                st.subheader("Motivos de bloqueio (RiskManager)")
                st.dataframe(reasons, use_container_width=True, hide_index=True)
            else:
                st.caption("Sem bloqueios pelo RiskManager nesta execução.")

            # Bloqueios por dia
            by_day = (dbg.get("blocked_by_day") or {}) if isinstance(dbg, dict) else {}
            if by_day:
                blocked_day_df = pd.DataFrame(sorted(by_day.items()), columns=["day", "blocked"])
                st.subheader("Bloqueios por dia (RiskManager)")
                st.dataframe(blocked_day_df, use_container_width=True, hide_index=True)
                st.bar_chart(blocked_day_df.set_index("day"))
            else:
                st.caption("Nenhum bloqueio por dia registrado.")

        # Trades e gráficos
        df = pd.DataFrame(bt.trades_log)
        if not df.empty:
            for col in ["entry_time", "exit_time"]:
                if col in df: df[col] = pd.to_datetime(df[col], errors="coerce")
            for col in ["entry_price", "exit_price", "qty", "fee", "pnl", "equity"]:
                if col in df: df[col] = pd.to_numeric(df[col], errors="coerce")

            st.subheader("Trades")
            cols_order = [c for c in ["entry_time","exit_time","side","entry_price","exit_price","qty","fee","pnl","equity","close_reason","stop_kind"] if c in df.columns]
            st.dataframe(df[cols_order] if cols_order else df, use_container_width=True, hide_index=True)

            csv_bytes = df.to_csv(index=False).encode("utf-8")
            st.download_button("⬇️ Baixar CSV de Trades", data=csv_bytes, file_name="backtest_trades.csv", mime="text/csv")

            if "equity" in df.columns:
                st.subheader("Curva de Equity")
                st.line_chart(df["equity"])

            st.subheader("Métricas")
            show_metrics(compute_metrics(df))

            # Sugestão automática de janelas (com base nas trades desta execução)
            with st.expander("💡 Sugerir janelas (horas/dias) com base neste período"):
                if "exit_time" in df.columns and df["exit_time"].notna().any():
                    dfh = df.copy()
                    dfh["hour"] = pd.to_datetime(dfh["exit_time"]).dt.hour
                    per_hour = dfh.groupby("hour")["pnl"].agg(["count","sum","mean"]).reset_index()
                    per_day = dfh.copy()
                    per_day["dow"] = pd.to_datetime(per_day["exit_time"]).dt.day_name()
                    per_day = per_day.groupby("dow")["pnl"].agg(["count","sum","mean"]).reset_index()
                    order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                    per_day["dow"] = pd.Categorical(per_day["dow"], categories=order, ordered=True)
                    per_day = per_day.sort_values("dow")

                    st.markdown("**Performance por hora (saída)**")
                    st.dataframe(per_hour.sort_values("mean", ascending=False), use_container_width=True, hide_index=True)

                    st.markdown("**Performance por dia da semana (saída)**")
                    st.dataframe(per_day, use_container_width=True, hide_index=True)

                    top_h = st.number_input("Selecionar top N horas por média PnL (mín. trades/hora: 50)",
                                            value=6, step=1, key="form_sugg_top_h", help=HELP["sugg_top_h"])
                    min_th = st.number_input("Mínimo de trades por hora",
                                             value=50, step=10, key="form_sugg_min_th", help=HELP["sugg_min_th"])
                    top_d = st.number_input("Selecionar top N dias por média PnL (mín. trades/dia: 100)",
                                            value=2, step=1, key="form_sugg_top_d", help=HELP["sugg_top_d"])
                    min_td = st.number_input("Mínimo de trades por dia",
                                             value=100, step=10, key="form_sugg_min_td", help=HELP["sugg_min_td"])

                    cand_hours = per_hour[per_hour["count"] >= min_th].sort_values("mean", ascending=False).head(int(top_h))["hour"].astype(int).tolist()
                    cand_days = per_day[per_day["count"] >= min_td].sort_values("mean", ascending=False).head(int(top_d))["dow"].astype(str).tolist()

                    st.write(f"**Horas sugeridas (UTC)**: {cand_hours}")
                    st.write(f"**Dias sugeridos**: {cand_days}")

                    if st.button("📋 Aplicar sugestões no formulário"):
                        st.session_state["form_hours"] = cand_hours
                        st.session_state["form_weekdays"] = cand_days
                        st.success("Sugestões aplicadas! Volte ao formulário para rodar.")
                else:
                    st.caption("Sem timestamps de saída suficientes para sugerir janelas.")
        else:
            st.warning("Nenhum trade registrado neste período/parâmetros.")

# ========= TAB: Otimização (mini‑sweep) =========
with tab_opt:
    st.subheader("Grid Search – SL/TP/Trail")
    st.caption("Dica: use o mesmo período/símbolo/timeframe da aba 'Rodar Backtest' para reaproveitar os candles (cache).")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        symbol_opt = st.text_input("Symbol",
                                   value=st.session_state.get("form_symbol", "BTC/USDT:USDT"),
                                   key="opt_symbol", help=HELP["symbol"])
    with c2:
        timeframe_opt = st.selectbox("Timeframe", ["1m","5m","15m","1h"],
                                     index=["1m","5m","15m","1h"].index(st.session_state.get("form_timeframe","5m")),
                                     key="opt_timeframe", help=HELP["timeframe"])
    with c3:
        start_opt = st.date_input("Início", value=st.session_state.get("form_start", date(2025,9,1)),
                                  key="opt_start", help=HELP["start"])
    with c4:
        end_opt = st.date_input("Fim", value=st.session_state.get("form_end", date(2025,9,29)),
                                key="opt_end", help=HELP["end"])

    c5, c6, c7 = st.columns(3)
    with c5:
        initial_opt = st.number_input("Capital inicial",
                                      value=float(st.session_state.get("form_initial",500.0)), step=50.0,
                                      key="opt_initial", help=HELP["initial"])
        commission_opt = st.number_input("Commission (fração por lado)",
                                         value=float(st.session_state.get("form_commission",0.0004)),
                                         step=0.0001, format="%.6f",
                                         key="opt_commission", help=HELP["commission"])
        slippage_opt = st.number_input("Slippage (pontos)",
                                       value=int(st.session_state.get("form_slippage",2)), step=1,
                                       key="opt_slippage", help=HELP["slippage"])
        testnet_opt = st.checkbox("Bybit Testnet",
                                  value=bool(st.session_state.get("form_testnet", True)),
                                  key="opt_testnet", help=HELP["testnet"])
    with c6:
        st.markdown("**Valores (lista separada por vírgula)**")
        sl_list_str = st.text_input("SL ATR Mult (lista)", value="1.6,1.7,1.8",
                                    key="opt_sl_list", help=HELP["grid_sl_list"])
        tp_list_str = st.text_input("TP R Mult (lista)", value="2.0,2.2,2.4",
                                    key="opt_tp_list", help=HELP["grid_tp_list"])
        tr_list_str = st.text_input("Trail ATR Mult (lista)", value="0.5,0.8,1.0",
                                    key="opt_tr_list", help=HELP["grid_tr_list"])
        bars_confirm_break_opt = st.number_input("Bars Confirm Break",
                                                 value=int(st.session_state.get("p_bcb",1)), step=1,
                                                 key="opt_bcb", help=HELP["bars_confirm_break"])
        min_atr_points_opt = st.number_input("Min ATR Points",
                                             value=int(st.session_state.get("p_minatr",6)), step=1,
                                             key="opt_minatr", help=HELP["min_atr_points"])
    with c7:
        use_be_opt = st.checkbox("Use BreakEven",
                                 value=bool(st.session_state.get("p_be", True)),
                                 key="opt_be", help=HELP["use_break_even"])
        be_r_opt = st.number_input("BreakEven R",
                                   value=float(st.session_state.get("p_ber",1.0)), step=0.1,
                                   key="opt_ber", help=HELP["break_even_r"])
        filter_ema_opt = st.checkbox("Filter EMA Slope",
                                     value=bool(st.session_state.get("p_ema", True)),
                                     key="opt_ema", help=HELP["filter_ema_slope"])
        min_ema_slope_opt = st.number_input("Min EMA Slope Pts",
                                            value=int(st.session_state.get("p_emaslope",3)), step=1,
                                            key="opt_emaslope", help=HELP["min_ema_slope_points"])
        use_trail_opt = st.checkbox("Use ATR Trailing",
                                    value=bool(st.session_state.get("p_atrtrail", True)),
                                    key="opt_atrtrail", help=HELP["use_atr_trailing"])

    st.markdown("---")
    c8, c9, c10 = st.columns(3)
    with c8:
        metric_target = st.selectbox("Métrica de ranking",
                                     ["net_pnl","profit_factor","expectancy","win_rate_%"],
                                     index=0, key="opt_metric_target", help=HELP["metric_target"])
        min_trades = st.number_input("Mínimo de trades", value=100, step=10,
                                     key="opt_min_trades", help=HELP["min_trades"])
    with c9:
        use_time_filters = st.checkbox("Usar filtros de tempo da aba Rodar", value=True,
                                       key="opt_use_time_filters", help=HELP["use_time_filters"])
        allowed_hours_opt = st.session_state.get("form_hours", [])
        allowed_days_opt = st.session_state.get("form_weekdays", [])
        st.caption(f"Horas permitidas atuais: {allowed_hours_opt or 'todas'}")
        st.caption(f"Dias permitidos atuais: {allowed_days_opt or 'todos'}")
    with c10:
        run_suggest = st.checkbox("🎯 Primeiro gerar sugestão de janelas e aplicar no grid",
                                  value=False, key="opt_run_suggest", help=HELP["run_suggest"])
        suggest_days = st.number_input("Sugestão: últimos N dias do período",
                                       value=7, step=1, key="opt_suggest_days", help=HELP["suggest_days"])
        suggest_topH = st.number_input("Sugestão: top N horas",
                                       value=6, step=1, key="opt_suggest_topH", help=HELP["suggest_topH"])
        suggest_minH = st.number_input("Sugestão: mín. trades/hora",
                                       value=50, step=10, key="opt_suggest_minH", help=HELP["suggest_minH"])
        suggest_topD = st.number_input("Sugestão: top N dias",
                                       value=2, step=1, key="opt_suggest_topD", help=HELP["suggest_topD"])
        suggest_minD = st.number_input("Sugestão: mín. trades/dia",
                                       value=100, step=10, key="opt_suggest_minD", help=HELP["suggest_minD"])

    sl_values = parse_float_list(sl_list_str)
    tp_values = parse_float_list(tp_list_str)
    tr_values = parse_float_list(tr_list_str)

    run_grid = st.button("🚀 Rodar mini‑sweep (grid)")

    if run_grid:
        st.info(f"🔎 Carregando candles: {symbol_opt} {timeframe_opt} de {start_opt} a {end_opt}")
        bars = get_bars_cached(symbol_opt, timeframe_opt, str(start_opt), str(end_opt))
        st.success(f"✅ Candles: {len(bars)}")

        # (Opcional) gerar sugestão de janelas com base nos últimos N dias
        hours_for_grid = allowed_hours_opt if use_time_filters else []
        days_for_grid = allowed_days_opt if use_time_filters else []

        if run_suggest and bars:
            # recorta últimos N dias do período
            last_ts = bars[-1].get("ts")
            if last_ts:
                cutoff = datetime.utcfromtimestamp(last_ts/1000) - timedelta(days=int(suggest_days))
                bars_suggest = [b for b in bars if datetime.utcfromtimestamp(b["ts"]/1000) >= cutoff]
            else:
                bars_suggest = bars

            # baseline rápido com config atual (sem filtros de tempo)
            cfg0 = deepcopy(CONFIG)
            cfg0.initial_balance = float(initial_opt)
            cfg0.symbol = symbol_opt
            cfg0.timeframe = timeframe_opt
            cfg0.commission_perc = float(commission_opt)
            cfg0.slippage_points = int(slippage_opt)
            if hasattr(cfg0, "risk") and hasattr(cfg0.risk, "max_trades_per_day"):
                cfg0.risk.max_trades_per_day = int(st.session_state.get("form_maxtrades", 200))

            sp0 = deepcopy(cfg0.strat_params)
            sp0.sl_atr_mult = float(st.session_state.get("p_sl",1.8))
            sp0.tp_r_mult = float(st.session_state.get("p_tp",2.2))
            sp0.bars_confirm_break = int(st.session_state.get("p_bcb",1))
            sp0.min_atr_points = int(st.session_state.get("p_minatr",6))
            sp0.filter_ema_slope = bool(st.session_state.get("p_ema", True))
            sp0.min_ema_slope_points = int(st.session_state.get("p_emaslope",3))
            sp0.use_break_even = bool(st.session_state.get("p_be", True))
            sp0.break_even_r = float(st.session_state.get("p_ber",1.0))
            sp0.use_atr_trailing = bool(st.session_state.get("p_atrtrail", True))
            sp0.trail_atr_mult = float(st.session_state.get("p_trail",0.5))
            sp0.allowed_hours = []
            sp0.allowed_weekdays = []
            cfg0.strat_params = sp0
            sm0 = StrategyManager(cfg0.strategy, params=sp0.__dict__)
            bt0 = Backtester(cfg0, sm0.get(), BybitCCXT(testnet=testnet_opt))
            with st.spinner("Calculando sugestão de janelas…"):
                _ = bt0.run(bars_suggest)
            dft = pd.DataFrame(bt0.trades_log)
            if not dft.empty and "exit_time" in dft.columns:
                dft["exit_time"] = pd.to_datetime(dft["exit_time"], errors="coerce")
                dft = dft.dropna(subset=["exit_time"])
                dft["hour"] = dft["exit_time"].dt.hour
                per_hour = dft.groupby("hour")["pnl"].agg(["count","sum","mean"]).reset_index()
                per_day = dft.copy()
                per_day["dow"] = dft["exit_time"].dt.day_name()
                per_day = per_day.groupby("dow")["pnl"].agg(["count","sum","mean"]).reset_index()
                order = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
                per_day["dow"] = pd.Categorical(per_day["dow"], categories=order, ordered=True)
                per_day = per_day.sort_values("dow")
                hours_for_grid = per_hour[per_hour["count"]>=int(suggest_minH)].sort_values("mean", ascending=False).head(int(suggest_topH))["hour"].astype(int).tolist()
                days_for_grid  = per_day[per_day["count"]>=int(suggest_minD)].sort_values("mean", ascending=False).head(int(suggest_topD))["dow"].astype(str).tolist()
                st.success(f"Horas sugeridas (UTC): {hours_for_grid} | Dias sugeridos: {days_for_grid}")
            else:
                st.warning("Não foi possível gerar sugestão (poucas trades). Seguindo sem filtro de tempo.")

        # Executa o grid
        combos = [(sl,tp,tr) for sl in sl_values for tp in tp_values for tr in tr_values]
        if not combos:
            st.error("Defina listas válidas para SL/TP/Trail.")
        else:
            st.write(f"Total de combinações: **{len(combos)}**")
            prog = st.progress(0)
            rows = []
            for idx, (sl, tp, tr) in enumerate(combos, start=1):
                cfg = deepcopy(CONFIG)
                cfg.initial_balance = float(initial_opt)
                cfg.symbol = symbol_opt
                cfg.timeframe = timeframe_opt
                cfg.commission_perc = float(commission_opt)
                cfg.slippage_points = int(slippage_opt)

                if hasattr(cfg, "risk") and hasattr(cfg.risk, "max_trades_per_day"):
                    cfg.risk.max_trades_per_day = int(st.session_state.get("form_maxtrades", 200))

                sp = deepcopy(cfg.strat_params)
                sp.sl_atr_mult = float(sl)
                sp.tp_r_mult = float(tp)
                sp.trail_atr_mult = float(tr)
                sp.bars_confirm_break = int(bars_confirm_break_opt)
                sp.min_atr_points = int(min_atr_points_opt)
                sp.filter_ema_slope = bool(filter_ema_opt)
                sp.min_ema_slope_points = int(min_ema_slope_opt)
                sp.use_break_even = bool(use_be_opt)
                sp.break_even_r = float(be_r_opt)
                sp.use_atr_trailing = bool(use_trail_opt)
                sp.allowed_hours = list(map(int, hours_for_grid)) if use_time_filters and hours_for_grid else (st.session_state.get("form_hours", []) if use_time_filters else [])
                sp.allowed_weekdays = list(map(str, days_for_grid)) if use_time_filters and days_for_grid else (st.session_state.get("form_weekdays", []) if use_time_filters else [])
                cfg.strat_params = sp

                sm = StrategyManager(cfg.strategy, params=sp.__dict__)
                bt = Backtester(cfg, sm.get(), BybitCCXT(testnet=testnet_opt))
                res = bt.run(bars)
                dft = pd.DataFrame(bt.trades_log)
                metrics = compute_metrics(dft) if not dft.empty else {"net_pnl":0.0,"profit_factor":None,"win_rate_%":0.0,"expectancy":0.0,"trades":0}
                row = {
                    "sl_atr_mult": sl,
                    "tp_r_mult": tp,
                    "trail_atr_mult": tr,
                    **metrics
                }
                rows.append(row)
                prog.progress(idx/len(combos))

            dfres = pd.DataFrame(rows)
            dfres = dfres[dfres["trades"] >= int(min_trades)]
            if dfres.empty:
                st.warning("Sem resultados com o mínimo de trades exigido.")
            else:
                if metric_target in ("profit_factor","expectancy","win_rate_%","net_pnl"):
                    dfres = dfres.sort_values(by=[metric_target,"net_pnl"], ascending=[False, False])
                else:
                    dfres = dfres.sort_values(by=["net_pnl"], ascending=False)

                st.subheader("Resultados do Grid")
                st.dataframe(dfres.reset_index(drop=True), use_container_width=True)

                best = dfres.iloc[0].to_dict()
                st.success(
                    f"🏆 Melhor combinação ({metric_target}): "
                    f"SL={best['sl_atr_mult']}, TP={best['tp_r_mult']}, Trail={best['trail_atr_mult']} | "
                    f"Trades={int(best['trades'])}, Net={best['net_pnl']:.2f}, PF={best.get('profit_factor')}, WR%={best.get('win_rate_%')}"
                )

                if st.button("📋 Aplicar melhor combinação ao formulário da aba 'Rodar'"):
                    st.session_state["p_sl"] = float(best["sl_atr_mult"])
                    st.session_state["p_tp"] = float(best["tp_r_mult"])
                    st.session_state["p_trail"] = float(best["trail_atr_mult"])
                    st.success("Parâmetros aplicados! Volte à aba 'Rodar Backtest'.")

# ========= TAB: Portfólio (multi‑ativos) =========
with tab_portfolio:
    st.subheader("Rodar backtest nas Memecoins")

    c0, c1 = st.columns([1.2, 2.8])
    with c0:
        timeframe_p = st.selectbox(
            "Timeframe", ["1m","5m","15m","1h"],
            index=["1m","5m","15m","1h"].index(st.session_state.get("form_timeframe","5m")),
            key="portfolio_timeframe", help=HELP["timeframe"]
        )
        start_p = st.date_input("Início", value=st.session_state.get("form_start", date(2025,9,1)),
                                key="portfolio_start", help=HELP["start"])
        end_p = st.date_input("Fim", value=st.session_state.get("form_end", date(2025,9,29)),
                              key="portfolio_end", help=HELP["end"])
        initial_p = st.number_input("Capital inicial (portfólio)",
                                    value=float(st.session_state.get("form_initial",500.0)), step=50.0,
                                    key="portfolio_initial", help=HELP["initial"])
        commission_p = st.number_input("Commission (fração por lado)",
                                       value=float(st.session_state.get("form_commission",0.0004)),
                                       step=0.0001, format="%.6f",
                                       key="portfolio_commission", help=HELP["commission"])
        slippage_p = st.number_input("Slippage (pontos)",
                                     value=int(st.session_state.get("form_slippage",2)), step=1,
                                     key="portfolio_slippage", help=HELP["slippage"])
        testnet_p = st.checkbox("Bybit Testnet",
                                value=bool(st.session_state.get("form_testnet", True)),
                                key="portfolio_testnet", help=HELP["testnet"])
        max_trades_day_p = st.number_input("Max trades/dia (Risk)",
                                           value=int(st.session_state.get("form_maxtrades", 200)), step=10,
                                           key="portfolio_maxtrades", help=HELP["max_trades_day"])
        st.markdown("**Filtros de tempo (entradas)**")
        hours_p = st.multiselect("Horas permitidas (UTC)", list(range(24)),
                                 default=st.session_state.get("form_hours", []),
                                 key="portfolio_hours", help=HELP["hours"])
        days_p = st.multiselect("Dias permitidos",
                                ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
                                default=st.session_state.get("form_weekdays", []),
                                key="portfolio_weekdays", help=HELP["weekdays"])
        st.markdown("---")
        st.markdown("**Heurística de 'memecoins'**")
        min_vol = st.number_input("Volume 24h mínimo (USD)", value=1_000_000, step=100_000,
                                  key="portfolio_min_vol", help=HELP["min_vol"])
        top_n = st.number_input("Top N por volume", value=50, step=5,
                                key="portfolio_top_n", help=HELP["top_n"])

    with c1:
        st.markdown("**Descoberta (Bybit perp linear USDT)**")
        if st.button("🔍 Buscar mercados e sugerir memecoins"):
            mkts = list_bybit_linear_usdt_perps_full()
            mems = filter_rank_memecoins(mkts, min_vol_usd=float(min_vol), top_n=int(top_n))
            st.session_state["memecoins_suggested"] = mems
            st.success(f"Encontrados {len(mems)} candidatos.")

        mems = st.session_state.get("memecoins_suggested", [])
        if mems:
            dfm = pd.DataFrame([{
                "symbol": m["symbol"], "base": m["base"], "vol24h_usd": m.get("vol24h_usd"), "active": m.get("active", True)
            } for m in mems])
            st.dataframe(dfm, use_container_width=True, hide_index=True)
            options = [m["symbol"] for m in mems]
            selected = st.multiselect("Selecione os símbolos para o portfólio",
                                      options=options, default=options[:8],
                                      key="portfolio_selected", help=HELP["portfolio_selected"])
        else:
            st.info("Clique em **Buscar mercados** para preencher a lista.")
            selected = []

    st.markdown("---")
    # --- Parâmetros da estratégia (comuns a todos os símbolos) ---
    st.subheader("Parâmetros da estratégia (comuns a todos os símbolos)")
    pc1, pc2, pc3 = st.columns(3)
    with pc1:
        sl_atr_mult_p = st.number_input("SL ATR Mult",
                                        value=float(st.session_state.get("p_sl", 1.8)), step=0.1,
                                        key="portfolio_sl", help=HELP["sl_atr_mult"])
        tp_r_mult_p = st.number_input("TP R Mult",
                                      value=float(st.session_state.get("p_tp", 2.2)), step=0.1,
                                      key="portfolio_tp", help=HELP["tp_r_mult"])
        trail_atr_mult_p = st.number_input("Trail ATR Mult",
                                           value=float(st.session_state.get("p_trail", 0.5)), step=0.1,
                                           key="portfolio_trail", help=HELP["trail_atr_mult"])
    with pc2:
        bars_confirm_break_p = st.number_input("Bars Confirm Break",
                                               value=int(st.session_state.get("p_bcb", 1)), step=1,
                                               key="portfolio_bcb", help=HELP["bars_confirm_break"])
        min_atr_points_p = st.number_input("Min ATR Points",
                                           value=int(st.session_state.get("p_minatr", 6)), step=1,
                                           key="portfolio_minatr", help=HELP["min_atr_points"])
        filter_ema_p = st.checkbox("Filter EMA Slope",
                                   value=bool(st.session_state.get("p_ema", True)),
                                   key="portfolio_ema", help=HELP["filter_ema_slope"])
    with pc3:
        use_be_p = st.checkbox("Use BreakEven",
                               value=bool(st.session_state.get("p_be", True)),
                               key="portfolio_be", help=HELP["use_break_even"])
        be_r_p = st.number_input("BreakEven R",
                                 value=float(st.session_state.get("p_ber", 1.0)), step=0.1,
                                 key="portfolio_ber", help=HELP["break_even_r"])
        use_trail_p = st.checkbox("Use ATR Trailing",
                                  value=bool(st.session_state.get("p_atrtrail", True)),
                                  key="portfolio_atrtrail", help=HELP["use_atr_trailing"])

    # Rodar portfólio
    run_port = st.button("🚀 Rodar Backtest do Portfólio")
    if run_port:
        if not selected:
            st.error("Selecione pelo menos um símbolo.")
        else:
            st.info(f"🔎 Baixando candles para {len(selected)} símbolos…")
            bars_by_symbol = get_bars_multi_cached(tuple(selected), timeframe_p, str(start_p), str(end_p))
            ok = any(bars_by_symbol.get(s) for s in selected)
            if not ok:
                st.error("Falha ao obter dados de OHLCV.")
            else:
                cfg_base = deepcopy(CONFIG)
                cfg_base.initial_balance = float(initial_p)
                cfg_base.timeframe = timeframe_p
                cfg_base.commission_perc = float(commission_p)
                cfg_base.slippage_points = int(slippage_p)
                if hasattr(cfg_base, "risk") and hasattr(cfg_base.risk, "max_trades_per_day"):
                    cfg_base.risk.max_trades_per_day = int(max_trades_day_p)

                sp = cfg_base.strat_params
                sp.sl_atr_mult = float(sl_atr_mult_p)
                sp.tp_r_mult = float(tp_r_mult_p)
                sp.trail_atr_mult = float(trail_atr_mult_p)
                sp.bars_confirm_break = int(bars_confirm_break_p)
                sp.min_atr_points = int(min_atr_points_p)
                sp.filter_ema_slope = bool(filter_ema_p)
                sp.use_break_even = bool(use_be_p)
                sp.break_even_r = float(be_r_p)
                sp.use_atr_trailing = bool(use_trail_p)
                sp.allowed_hours = list(map(int, hours_p)) if hours_p else []
                sp.allowed_weekdays = list(map(str, days_p)) if days_p else []

                from r2d2.portfolio_backtester import PortfolioBacktester
                pbt = PortfolioBacktester(cfg_base, exchange_factory=lambda: BybitCCXT(testnet=testnet_p),
                                          strategy_cfg=sp.__dict__)
                with st.spinner("Executando backtests por símbolo e agregando resultados…"):
                    summary = pbt.run(bars_by_symbol)

                if "error" in summary:
                    st.error(summary["error"])
                else:
                    st.success("✅ Portfólio concluído!")

                    st.json(summary)

                    per_symbol = pd.DataFrame(summary.get("per_symbol", []))
                    if not per_symbol.empty:
                        st.subheader("Desempenho por símbolo")
                        st.dataframe(per_symbol.sort_values("net_pnl", ascending=False),
                                     use_container_width=True, hide_index=True)

                    dft = pd.DataFrame(pbt.portfolio_trades)
                    if not dft.empty:
                        for col in ["entry_time","exit_time"]:
                            if col in dft: dft[col] = pd.to_datetime(dft[col], errors="coerce")
                        for col in ["entry_price","exit_price","qty","fee","pnl","equity"]:
                            if col in dft: dft[col] = pd.to_numeric(dft[col], errors="coerce")

                        st.subheader("Trades do portfólio (todas)")
                        cols = [c for c in ["symbol","entry_time","exit_time","side","entry_price","exit_price","qty","fee","pnl","equity","close_reason","stop_kind"] if c in dft.columns]
                        st.dataframe(dft[cols] if cols else dft, use_container_width=True, hide_index=True)

                        csv_bytes = dft.to_csv(index=False).encode("utf-8")
                        st.download_button("⬇️ Baixar CSV de Trades (portfólio)", data=csv_bytes,
                                           file_name="portfolio_trades.csv", mime="text/csv")

                        if pbt.portfolio_equity_curve is not None and not pbt.portfolio_equity_curve.empty:
                            st.subheader("Curva de Equity do Portfólio")
                            st.line_chart(pbt.portfolio_equity_curve.set_index("exit_time"))
                    else:
                        st.info("Sem trades registradas no portfólio.")

# ========= TAB: Histórico =========
with tab_history:
    st.subheader("Backtests anteriores (Supabase)")
    sb = SupabaseStore()
    st.caption(f"Supabase: {'✅ conectado' if sb.enabled else '❌ indisponível'}")

    hc1, hc2, hc3 = st.columns([1, 1, 1])
    with hc1:
        filt_symbol = st.text_input("Filtrar por Symbol", value="", key="hist_symbol", help=HELP["symbol"])
    with hc2:
        filt_timeframe = st.text_input("Filtrar por Timeframe", value="", key="hist_timeframe", help=HELP["timeframe"])
    with hc3:
        limit = st.number_input("Máximo de registros", value=50, step=10, key="hist_limit",
                                help="Quantos backtests recentes carregar da base.")

    if st.button("🔄 Recarregar histórico", use_container_width=False):
        st.cache_data.clear()

    backtests = supabase_fetch_backtests(sb, symbol=filt_symbol or None, timeframe=filt_timeframe or None, limit=int(limit))
    if not backtests:
        st.info("Nenhum backtest encontrado.")
    else:
        df_bt = pd.DataFrame(backtests)
        show_cols = [c for c in ["id","created_at","strategy","symbol","timeframe","initial_balance","final_balance","pnl","trades","wins","losses"] if c in df_bt.columns]
        st.dataframe(df_bt[show_cols].sort_values(by=show_cols[0], ascending=False) if show_cols else df_bt,
                     use_container_width=True, hide_index=True)

        ids = df_bt["id"].tolist() if "id" in df_bt.columns else []
        selected_id = st.selectbox("Selecionar Backtest", ids, key="hist_select_id",
                                   help="Escolha um backtest para ver trades e parâmetros.") if ids else None

        if selected_id is not None:
            st.markdown(f"### Detalhes do Backtest #{selected_id}")
            trades = supabase_fetch_trades(sb, selected_id)
            df_tr = pd.DataFrame(trades)

            if not df_tr.empty:
                for col in ["entry_time","exit_time"]:
                    if col in df_tr: df_tr[col] = pd.to_datetime(df_tr[col], errors="coerce")
                for col in ["entry_price","exit_price","qty","fee","pnl","equity"]:
                    if col in df_tr: df_tr[col] = pd.to_numeric(df_tr[col], errors="coerce")

                st.dataframe(df_tr, use_container_width=True, hide_index=True)

                st.subheader("Métricas do backtest selecionado")
                show_metrics(compute_metrics(df_tr))

                if "equity" in df_tr.columns and df_tr["equity"].notna().any():
                    st.subheader("Curva de Equity")
                    st.line_chart(df_tr["equity"])

                csv_bytes = df_tr.to_csv(index=False).encode("utf-8")
                st.download_button(f"⬇️ Baixar CSV Trades #{selected_id}", data=csv_bytes,
                                   file_name=f"trades_{selected_id}.csv", mime="text/csv")
            else:
                st.info("Sem trades associados (ou não encontrados).")

            st.markdown("#### Parâmetros desta execução")
            params_obj = None
            if "params" in df_bt.columns:
                params_obj = df_bt.loc[df_bt["id"] == selected_id, "params"].iloc[0]
                try:
                    if isinstance(params_obj, str):
                        params_obj = json.loads(params_obj)
                except Exception:
                    pass
            st.code(json.dumps(params_obj or {}, indent=2), language="json")

            if st.button("📋 Carregar estes parâmetros no formulário", type="primary"):
                if isinstance(params_obj, dict):
                    st.session_state["p_sl"]      = float(params_obj.get("sl_atr_mult", st.session_state.get("p_sl", 1.8)))
                    st.session_state["p_tp"]      = float(params_obj.get("tp_r_mult", st.session_state.get("p_tp", 2.2)))
                    st.session_state["p_bcb"]     = int(params_obj.get("bars_confirm_break", st.session_state.get("p_bcb", 1)))
                    st.session_state["p_minatr"]  = int(params_obj.get("min_atr_points", st.session_state.get("p_minatr", 6)))
                    st.session_state["p_ema"]     = bool(params_obj.get("filter_ema_slope", st.session_state.get("p_ema", True)))
                    st.session_state["p_emaslope"]= int(params_obj.get("min_ema_slope_points", st.session_state.get("p_emaslope", 3)))
                    st.session_state["p_be"]      = bool(params_obj.get("use_break_even", st.session_state.get("p_be", True)))
                    st.session_state["p_ber"]     = float(params_obj.get("break_even_r", st.session_state.get("p_ber", 1.0)))
                    st.session_state["p_atrtrail"]= bool(params_obj.get("use_atr_trailing", st.session_state.get("p_atrtrail", True)))
                    st.session_state["p_trail"]   = float(params_obj.get("trail_atr_mult", st.session_state.get("p_trail", 0.5)))
                    st.success("Parâmetros carregados na aba 'Rodar Backtest'.")
                else:
                    st.warning("Parâmetros não disponíveis/ilegíveis para este registro.")
# ========= TAB: Ajuda =========
with tab_help:
    st.header("Ajuda • Ensinamentos do mestre Yoda")

    st.caption("O maior professor, o fracasso é.")

    # --- Glossário com busca/filtros ---
    st.subheader("Glossário")
    _render_glossary(GLOSSARY)

    # Downloads do glossário e dos parâmetros
    colg1, colg2 = st.columns(2)
    with colg1:
        try:
            gloss_df = pd.DataFrame(GLOSSARY)
            st.download_button("⬇️ Baixar Glossário (CSV)", data=gloss_df.to_csv(index=False).encode("utf-8"),
                               file_name="glossario_r2d2.csv", mime="text/csv", key="help_dl_gloss")
        except Exception:
            st.caption("Não foi possível gerar CSV do glossário agora.")
    with colg2:
        try:
            params_df = _params_help_dataframe()
            st.download_button("⬇️ Baixar Explicações dos Parâmetros (CSV)", data=params_df.to_csv(index=False).encode("utf-8"),
                               file_name="parametros_r2d2.csv", mime="text/csv", key="help_dl_params")
        except Exception:
            st.caption("Não foi possível gerar CSV dos parâmetros agora.")

    st.markdown("---")

    # --- Parâmetros do app (explicados) ---
    st.subheader("Parâmetros do app — explicações")
    st.caption("Os mesmos textos dos tooltips, organizados em tabela para consulta rápida.")
    try:
        st.dataframe(_params_help_dataframe(), use_container_width=True, hide_index=True)
    except Exception:
        st.info("Tabela de parâmetros indisponível.")

    st.markdown("---")

    # --- Anatomia de uma trade ---
    _render_trade_anatomy()

    st.markdown("---")

    # --- FAQ ---
    _render_faq()

    st.markdown("— Fim —")
