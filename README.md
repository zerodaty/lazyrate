# lazyrate

> Tasa oficial del BCV y Binance P2P (USDT/VES) en la barra superior de GNOME y en una TUI
> estilo [lazydocker](https://github.com/jesseduffield/lazydocker).

[![Release](https://img.shields.io/github/v/release/zerodaty/lazyrate)](https://github.com/zerodaty/lazyrate/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/zerodaty/lazyrate/ci.yml?branch=main&label=CI)](https://github.com/zerodaty/lazyrate/actions)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

## ¿Qué muestra?

- **Tasa oficial del BCV** — USD, EUR, CNY, TRY y RUB, leídas directamente del Excel
  oficial "otras monedas" que publica el Banco Central de Venezuela. Cuando el BCV
  publica la tasa del día siguiente por la tarde, lazyrate también la captura y la
  muestra como "próxima".
- **USDT/VES de Binance P2P** — promedio ponderado por cantidad sobre ~100 anuncios,
  con filtro de outliers por rango intercuartílico (IQR) para descartar precios anzuelo.

Y lo muestra en dos lugares:

1. **La barra superior de GNOME**, vía AppIndicator: un texto configurable tipo
   `BCV 108,52 | P2P 130,04` que se refresca solo, con menú para abrir la TUI o
   forzar una actualización.
2. **Una TUI estilo lazydocker** con gráfica histórica y panel de estadísticas:
   variación del día, promedios de 7 y 30 días, mínimo/máximo, tendencia
   (subiendo ↑ / bajando ↓ / estable →) y brecha BCV↔P2P.

Además, `lazyrate backfill` importa el **histórico oficial del BCV del año completo**
(desde el primer día hábil del año) a partir de los Excel trimestrales que publica el
propio banco, para que la gráfica tenga contexto desde la primera ejecución.

## Capturas

![Barra de GNOME](docs/img/bar.png)

![TUI](docs/img/tui.gif)

<!-- TODO: grabar con vhs -->

## Instalación

### Ubuntu / Debian (recomendado)

Descarga el `.deb` desde [Releases](https://github.com/zerodaty/lazyrate/releases) e instala:

```bash
sudo apt install ./lazyrate_*.deb
```

El paquete instala el indicador de la barra, lo deja autoarrancado en cada sesión y
trae las dependencias del sistema (PyGObject/AppIndicator) ya resueltas.

### Fedora (y otras distros)

```bash
pipx install lazyrate
```

En GNOME ≥ 41 necesitas además la extensión
[AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/)
para que el indicador aparezca en la barra.

### Desde el código

```bash
pipx install git+https://github.com/zerodaty/lazyrate
```

## Uso

```bash
lazyrate                      # abre la TUI
lazyrate fetch                # consulta y guarda las tasas ahora (BCV + Binance)
lazyrate fetch --source bcv   # solo una fuente (bcv | binance)
lazyrate history --days 30    # histórico guardado, en la terminal
lazyrate backfill             # importa el histórico BCV del año (--year para otro año)
lazyrate autostart enable     # autoarranque del indicador (enable | disable | status)
lazyrate-indicator            # daemon del indicador de GNOME (en primer plano)
```

Con el `.deb`, `lazyrate-indicator` se autoarranca al iniciar sesión; no hace falta
lanzarlo a mano. Con pipx, actívalo con `lazyrate autostart enable`.

## Configuración

El archivo es `~/.config/lazyrate/config.toml`; se crea con los valores por defecto la
primera vez que se ejecuta cualquier comando.

| Clave | Default | Descripción |
| --- | --- | --- |
| `general.refresh_minutes` | `20` | Minutos entre actualizaciones automáticas (indicador y TUI). |
| `general.decimals` | `2` | Decimales al mostrar tasas en la barra. |
| `general.retention_days` | `365` | Días de histórico que se conservan en la base de datos. |
| `bar.format` | `"BCV {bcv_usd} \| P2P {binance_usdt}"` | Plantilla del texto de la barra. Placeholders: `{bcv_usd}`, `{bcv_eur}`, `{bcv_cny}`, `{bcv_try}`, `{bcv_rub}`, `{binance_usdt}`. |
| `bar.stale_mark` | `true` | Añade una marca cuando los datos llevan demasiado tiempo sin refrescarse. |
| `bcv.enabled` | `true` | Consultar la tasa oficial del BCV. |
| `bcv.currencies` | `["USD"]` | Monedas del BCV a seguir: `USD`, `EUR`, `CNY`, `TRY`, `RUB`. |
| `bcv.publish_hour` | `18` | Hora (America/Caracas) desde la que se busca también la tasa del día siguiente. |
| `binance.enabled` | `true` | Consultar Binance P2P. |
| `binance.asset` | `"USDT"` | Activo a cotizar en Binance P2P. |
| `binance.trade_type` | `"SELL"` | Lado del libro: `SELL` (vender USDT por Bs) o `BUY`. |
| `binance.merchant_only` | `true` | Considerar solo anuncios de comerciantes verificados. |
| `binance.max_ads` | `100` | Máximo de anuncios a promediar. |

Los datos se guardan en rutas XDG estándar: histórico en
`~/.local/share/lazyrate/history.db` (SQLite) y logs en `~/.local/state/lazyrate/`.

## Atajos de la TUI

| Tecla | Acción |
| --- | --- |
| `q` | Salir |
| `r` | Refrescar (consulta las fuentes ahora; si la BD está vacía, además hace el backfill) |
| `c` | Abrir la pantalla de configuración |
| `b` | Comparar fuentes (superpone BCV y Binance en la gráfica) |
| `7` / `3` / `9` / `a` | Rango de la gráfica: 7, 30, 90 días o todo |
| `Tab` | Cambiar de panel |
| `↑`/`↓` o `j`/`k` | Moverse por la lista |

## Nota sobre el certificado SSL del BCV

La web del BCV suele servir una cadena de certificados rota (falta el intermedio), por
lo que la verificación TLS estricta falla en muchos sistemas. lazyrate intenta
**siempre** primero con verificación completa y, solo si falla por ese motivo,
reintenta sin verificar — acotado exclusivamente al dominio `bcv.org.ve`. Nunca se
desactiva la verificación de forma global ni para Binance.

## Desarrollo

```bash
git clone https://github.com/zerodaty/lazyrate
cd lazyrate
python3 -m venv --system-site-packages .venv   # --system-site-packages por PyGObject/GTK
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

Para construir el paquete Debian:

```bash
ln -s packaging/debian debian
dpkg-buildpackage -us -uc -b
```

## Licencia

[MIT](LICENSE) — Frany Velasquez ([github.com/zerodaty](https://github.com/zerodaty)).

## About

lazyrate is a lightweight Python app for Venezuelan users (and anyone tracking the
bolívar): it shows the official BCV exchange rate and the Binance P2P USDT/VES rate in
the GNOME top bar via AppIndicator, plus a lazydocker-style TUI with historical charts
and statistics. Data comes straight from the official BCV Excel files and the public
Binance P2P search endpoint, stored locally in SQLite. MIT licensed.
