# Discord Trading Tools

Bot de Discord para calculos operativos de trading. Incluye un planificador de entradas por fases, calculo de riesgo y un scanner micro-cap configurable para publicar oportunidades en un canal.

> No es recomendacion financiera. Es una herramienta operativa para investigacion y seguimiento.

## Features

- Slash command `/plan-trading` para calcular fases de entrada.
- Break-even acumulado por etapa con comision configurable.
- Riesgo por fase, acciones por fase, stop price, take profit y entrada media ponderada.
- Scanner micro-cap con filtros configurables desde Discord.
- Limpieza opcional del canal antes de publicar el scanner.
- Logica de calculo separada del adaptador de Discord y cubierta con tests.

## Requisitos

- Python 3.11 o superior.
- Un bot creado en Discord Developer Portal.
- Permisos de Discord para usar slash commands.
- Para limpiar canales, el bot necesita `Manage Messages` y `Read Message History`.

## Instalacion

```powershell
git clone https://github.com/FloDevTech/Discort-trading-bot.git
cd Discort-trading-bot

python -m venv venv
.\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuracion

Crea o edita el archivo `.env`. El bot lo carga automaticamente al arrancar. Como minimo necesitas:

```env
DISCORD_TOKEN=tu_token_de_discord
```

Opcionalmente, para sincronizar los slash commands solo en un servidor de pruebas:

```env
DISCORD_GUILD_ID=id_de_tu_servidor
```

Para activar la publicacion automatica del scanner:

```env
DISCORD_STOCK_SCANNER_CHANNEL_ID=id_del_canal
STOCK_SCANNER_INTERVAL_MINUTES=5
```

## Ejecutar

```powershell
$env:PYTHONPATH="src"
python -m trading_bot.bot
```

## Comandos

### `/plan-trading`

Calcula un plan por fases:

```text
/plan-trading fases:3 riesgo_total:5 entradas:0.52,0.53,0.54 margenes:0.05,0.05,0.05 porcentajes:25,35,40 r_objetivo:3 comision:0.005
```

Parametros:

- `fases`: cantidad de etapas.
- `riesgo_total`: riesgo total disponible en dolares.
- `entradas`: precios de entrada separados por coma.
- `margenes`: margen al stop por etapa, separado por coma.
- `porcentajes`: porcentaje del riesgo total asignado a cada etapa. Debe sumar 100.
- `r_objetivo`: multiplo R para calcular take profit. Por defecto es `3`.
- `comision`: comision por accion. Es opcional; si no la pasas, usa la ultima comision escrita durante la sesion actual del bot.

El resultado incluye:

- Riesgo por fase.
- Acciones por fase.
- Stop price por fase.
- Break-even acumulado por fase, incluyendo comision.
- Entrada media ponderada.
- Take profit medio del plan: `entrada_media + (riesgo_total * r_objetivo)`.
- Take profit por fase acumulada: `entrada_media_acumulada + (riesgo_acumulado * r_objetivo)`.
- Acciones totales.

Ejemplo: si en fase 2 el riesgo acumulado es `$3`, el objetivo es `3R` y la entrada media acumulada es `$4.2667`, el TP de esa fase es `$13.2667`.

### Scanner micro-cap

Ejecutar scanner manualmente:

```text
/scanner-preview
```

Ver configuracion actual:

```text
/scanner-config
```

Actualizar filtros:

```text
/scanner-set max_price:2 min_volume:500000 min_float_rotation:0.5
/scanner-set min_price:.1
/scanner-set min_change_percent:50
/scanner-set max_symbols:120 limit:10 interval_minutes:5
/scanner-set symbols:DFSC,MDXH,SURG
/scanner-set symbols:auto
```

Limpiar mensajes del canal actual:

```text
/clean
/clean limit:500
```

## Variables de entorno del scanner

```powershell
$env:STOCK_SCANNER_MAX_PRICE="2"
$env:STOCK_SCANNER_MIN_PRICE="0.05"
$env:STOCK_SCANNER_MAX_MARKET_CAP="150000000"
$env:STOCK_SCANNER_MIN_MARKET_CAP="1000000"
$env:STOCK_SCANNER_MIN_VOLUME="500000"
$env:STOCK_SCANNER_MIN_CHANGE_PERCENT="50"
$env:STOCK_SCANNER_MIN_FLOAT_ROTATION="0.5"
$env:STOCK_SCANNER_LIMIT="10"
$env:STOCK_SCANNER_MAX_SYMBOLS="120"
$env:STOCK_SCANNER_SYMBOLS="DFSC,MDXH,ENSC,BZAI,MVST"
$env:STOCK_SCANNER_CLEAR_LIMIT="100"
```

Si `STOCK_SCANNER_SYMBOLS` no esta definido, el scanner intenta obtener simbolos desde el screener publico de Finviz y luego enriquece los datos de cada ticker. Yahoo Finance queda como fallback limitado para precio y volumen.

Los cambios hechos desde `/scanner-set` se guardan en `.env`, asi se conservan al reiniciar el bot.

## Tests

```powershell
$env:PYTHONPATH="src"
python -m unittest discover -s tests
```

## Estructura

```text
src/trading_bot/
  bot.py                 # Adaptador Discord y slash commands
  formatters.py          # Respuestas formateadas para Discord
  core/
    risk.py              # Calculos puros del plan de trading
    scanner_config.py    # Configuracion persistente del scanner
    stock_scanner.py     # Scanner micro-cap
tests/
  test_risk.py
  test_formatters.py
  test_scanner_config.py
  test_stock_scanner.py
```

## Seguridad

No subas tokens ni credenciales. Usa `.env` para valores reales y `.env.example` solo para placeholders.
