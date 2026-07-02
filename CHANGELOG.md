# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/);
versionado [SemVer](https://semver.org/lang/es/).

## [Unreleased]

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
