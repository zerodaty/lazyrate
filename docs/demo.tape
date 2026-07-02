# Demo de lazyrate para el README — regenerar con: vhs docs/demo.tape
# (requiere vhs, ttyd y ffmpeg; binarios sueltos en ~/.local/bin sirven)

Output docs/img/tui.gif

Set FontSize 15
Set Width 1200
Set Height 680
Set Theme "Catppuccin Mocha"
Set TypingSpeed 60ms
Set Framerate 24
Set Padding 12

# PATH del usuario (pipx) sin que salga en la grabación
Hide
Type "export PATH=$HOME/.local/bin:$PATH && clear"
Enter
Show

Type "lazyrate"
Sleep 800ms
Enter
Sleep 4s

# Todo el histórico del año (backfill del BCV)
Type "a"
Sleep 3s

# Cambiar a la serie de Binance P2P
Down
Sleep 2.5s

# Comparar BCV vs Binance (la brecha, visual)
Type "b"
Sleep 3.5s

# Pantalla de configuración
Type "c"
Sleep 3s
Escape
Sleep 1s

# Cerrar en el dashboard a 30 días
Type "3"
Sleep 2.5s
