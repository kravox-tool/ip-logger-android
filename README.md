# 🛡️ IP Logger — App Android (Terminal)

App Android con interfaz de terminal que ejecuta un servidor Flask + túnel
Cloudflare (`trycloudflare.com`) para capturar IP y User-Agent y redirigir
al enlace que elijas.

## 📦 Cómo generar el APK (sin instalar nada en tu PC)

1. Crea un repo en GitHub y sube **toda** esta carpeta.
2. Entra a la pestaña **Actions** → workflow **Build APK** → **Run workflow**.
3. Espera ~6-10 minutos.
4. Descarga el APK desde **Artifacts → ip-logger-apk**.

Para generar una *Release* con el APK adjunto, sube un tag:

```bash
git tag v1.0.0
git push origin v1.0.0
```

## 📲 Instalación

Copia el `app-debug.apk` al teléfono, actívalo con "Instalar apps de origen
desconocido" y ábrelo. Requiere **Android 7.0 (API 24)** o superior y
arquitectura **arm64-v8a** (cualquier móvil moderno).

## 🕹️ Uso

1. Abre la app (verás la terminal negra).
2. Pega tu enlace de destino (ej. `https://youtube.com`) y pulsa Enter.
3. Espera a que aparezca **LINK PARA TU OBJETIVO** — ya está copiado al portapapeles.
4. Comparte ese enlace. Cada clic se registra con IP, User-Agent y hora.

Comandos: `link`, `logs`, `clear`, `ayuda`, `salir`.

Los registros se guardan en `registro_ips.txt` dentro del almacenamiento
privado de la app.

## 🔧 Notas técnicas

- **Python 3.11 + Flask** embebidos con Chaquopy.
- **cloudflared** (binario estático oficial de Cloudflare) se empaqueta en
  `jniLibs` como `libcloudflared.so`; `extractNativeLibs=true` permite ejecutarlo.
- El terminal es **xterm.js** dentro de un WebView, con puente JS↔Kotlin↔Python.
- Si el `subprocess` de Python falla en algún dispositivo, hay un plan B que
  lanza `cloudflared` desde Java (`ProcessBuilder`).
- Si `flask` no estuviera disponible, se usa un servidor `http.server` interno
  equivalente (misma lógica de captura y redirección).
