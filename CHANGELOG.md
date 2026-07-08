# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/);
versionado [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Added

- `lazyrate now [--json] [--source bcv|binance]`: snapshot instantáneo desde la
  base local (sin red) con tasa vigente, variación del día, "próxima" del BCV y
  brecha BCV↔P2P. La salida `--json` está pensada para scripts y barras de estado
  (waybar, polybar, `watch`).
- La lista de fuentes de la TUI es ahora un mini-dashboard: cada par muestra su
  tasa vigente y la variación del día con color (sube rojo / baja verde).
- Fila "Próxima" en las estadísticas de la TUI cuando el BCV ya publicó la tasa
  del día siguiente (igual que hace el menú del indicador).

### Changed

- Rendimiento: el esquema SQLite se crea una sola vez por proceso —antes cada
  consulta re-ejecutaba el DDL— y WAL usa `synchronous=NORMAL` (~3× más rápido
  por consulta, notable en el recálculo por tecla de la calculadora).
- `format_pct` vive ahora en `lazyrate.format` (capa pura, reutilizable desde la
  CLI); `lazyrate.tui.widgets` lo re-exporta.

### Fixed

- Las estadísticas ("Actual", variación, promedios) ya no saltan a la fecha valor
  futura cuando el BCV publica la tasa del día siguiente: lo vigente y lo próximo
  se muestran por separado.

## [0.2.0] - 2026-07-05

### Added

- Calculadora de conversión integrada en la TUI, como una pestaña "Calculadora"
  junto a "Fuentes" (o la tecla `=`). Convierte un monto comparando dos tasas
  seleccionables en ambos sentidos (divisa→Bs y Bs→divisa) y muestra el % de
  disparidad; el panel derecho grafica en paralelo las dos tasas elegidas con sus
  estadísticas de brecha. Por defecto compara BCV USD con Binance USDT, pero el par
  y la dirección son configurables y se recuerdan entre sesiones (sección `[calc]`
  del `config.toml`). No consulta la red: usa solo el histórico local.

### Changed

- "Abrir historial" del indicador abre la terminal con un tamaño holgado (120×34);
  antes el 80×24 por defecto dejaba la TUI apretada.

### Fixed

- README: la instalación con pipx ahora indica `--system-site-packages` y el extra
  `[tui]`, e instala desde el repositorio (el paquete no está en PyPI); el comando
  anterior dejaba el indicador sin PyGObject y sin la interfaz de terminal.

## [0.1.1] - 2026-07-02

### Fixed

- "Abrir historial" del indicador ahora resuelve la ruta absoluta de la TUI;
  antes fallaba cuando `lazyrate` no estaba en el PATH de gnome-terminal
  (instalaciones con venv/pipx).
- `lazyrate autostart` escribe la ruta absoluta del indicador en el `.desktop`
  (el PATH de la sesión de GNOME no siempre incluye `~/.local/bin`).
- El texto del indicador se restaura al despertar de la suspensión (señal
  `PrepareForSleep` de logind + re-pintado periódico del label) y se consulta
  la tasa de inmediato al reanudar.

## [0.1.0] - 2026-07-01

### Added

- Proveedor BCV: descarga y parseo del Excel trimestral oficial (USD, EUR, CNY, TRY, RUB),
  con caché local y backfill del histórico del año.
- Proveedor Binance P2P: promedio ponderado por cantidad con filtro de outliers (IQR)
  sobre anuncios USDT/VES.
- Indicador para la barra de GNOME (AppIndicator) con menú y autostart.
- TUI estilo lazydocker (`lazyrate`): gráfica de evolución, estadísticas y configuración.
- CLI: `fetch`, `history`, `backfill`, `autostart`.
- Histórico en SQLite y configuración TOML (rutas XDG).
