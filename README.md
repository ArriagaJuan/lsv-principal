# LSV principal con Arduino TTL

La aplicación permite adquirir lecturas de velocidad de un sensor LSV mediante RS232 o TCP, calcular la distancia acumulada y organizar la adquisición por ciclos. Integra el control de pulsos TTL con Arduino Uno y exporta los resultados a Excel.

## Funciones

- Configuración de duración, ciclos, pausas e intervalo de lectura.
- Visualización de velocidad en m/min, distancia en metros y tiempos por muestra.
- Control del trigger Arduino TTL V1 en los canales D12 y D10.
- Respaldo incremental en JSONL y exportación a Excel con resumen, intentos y registro TTL.
- Desfase temporal manual y conservación del tiempo bruto de las lecturas.
- Modo Simulación con datos sintéticos, identificado en los registros.

## Requisitos

- Windows y Python 3.11 o 3.12 con pip y soporte para entornos virtuales.
- Dependencias de `requirements.txt`: PySide6, pyserial y openpyxl.
- Conexión a Internet durante la instalación de dependencias.
- Para adquirir datos desde instrumentos: sensor LSV compatible con consultas `v` y respuestas numéricas en m/min, conexión RS232 o TCP y Arduino Uno con el firmware TTL V1 incluido.
- Arduino IDE y controlador USB de la placa para cargar el firmware.

La simulación permite utilizar la interfaz sin instrumentos conectados. El campo Divisor DAQ se conserva como referencia; no programa el DAQ del sensor.

## Instalación

1. Descargue el repositorio mediante **Code > Download ZIP** y extraiga su contenido, o clone el repositorio.
2. Instale Python 3.11 o 3.12 con la opción de agregar Python a PATH.
3. Ejecute `ejecutar.bat`. El lanzador crea `.venv`, instala las dependencias e inicia la aplicación. Utilice el mismo archivo para los siguientes arranques.

Instalación manual desde PowerShell, dentro de la carpeta del programa:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe sincronizador_laser_lsv.py
```

## Uso de la aplicación

1. Inicie la aplicación con `ejecutar.bat`.
2. Seleccione **Carpeta de exportación** para elegir el destino de los resultados.
3. Configure segundos por ciclo, cantidad de ciclos, pausa e intervalo de lectura. El intervalo mínimo es de 0.5 segundos.
4. Mantenga **Simulación** activada para trabajar con datos sintéticos. Para adquirir lecturas del LSV, desactive esta opción, seleccione RS232 o TCP e indique el puerto serie o el host y puerto TCP correspondientes al equipo.
5. Para la adquisición con instrumentos, seleccione el puerto del Arduino y pulse **Conectar LSV** y **Conectar trigger TTL V1**. Configure una duración mayor que cero en al menos uno de los canales D12 o D10, expresada en microsegundos.
6. Pulse **Iniciar adquisición**. La tabla muestra las muestras y la aplicación guarda un respaldo JSONL durante la sesión.
7. Utilice **Detener / cancelar** para interrumpir la adquisición cuando sea necesario.
8. Al finalizar, pulse **Exportar Excel**. Los archivos utilizan nombres únicos para conservar exportaciones anteriores.

El desfase manual modifica el tiempo alineado y conserva el tiempo bruto. Los datos generados en Simulación se identifican como sintéticos.

## Arduino Uno y trigger TTL V1

1. Abra `arduino/trigger_ttl_controller/trigger_ttl_controller.ino` en Arduino IDE.
2. Seleccione la placa **Arduino Uno** y su puerto COM; cargue el sketch.
3. Cierre el Monitor Serie antes de conectar la aplicación al mismo puerto.

El firmware utiliza 9600 baudios. D12 y D10 son salidas TTL de aproximadamente 0/5 V; D13 corresponde al buzzer. Utilice entradas compatibles con esos niveles y la conexión de referencia eléctrica correspondiente.

Al comenzar cada ciclo, la aplicación envía un pulso con la duración configurada para cada canal; al terminar envía `RESET`. Un valor de cero deshabilita ese canal. Los pulsos se generan al inicio del ciclo y no permanecen activos durante toda la adquisición. La confirmación serie `OK,PULSE` indica recepción del comando.

Para consultar el estado del Arduino, utilice **Consultar Arduino (sin disparar)** o `DIAGNOSTICO_ARDUINO.bat`. La interfaz independiente del trigger se inicia con `abrir_trigger_arduino.bat`; utiliza Tkinter, incluido en la instalación estándar de Python para Windows.

## Captura auxiliar Hentschel 373

`capturar_hentschel_373.py` permite recibir bytes desde un puerto serie y guardarlos en un archivo JSONL con fecha UTC, marca de tiempo monotónica, longitud y contenido hexadecimal. La herramienta funciona por línea de comandos y no transmite órdenes al instrumento.

```powershell
.\.venv\Scripts\python.exe capturar_hentschel_373.py --puerto COM5 --baudios 9600 --segundos 10 --salida captura_hentschel.jsonl
```

Sustituya el puerto y los baudios por los parámetros del instrumento. La captura Hentschel es independiente de la interfaz principal; conserva los bytes recibidos sin interpretarlos ni incorporarlos a las mediciones LSV.

## Herramientas auxiliares

Para instalar las dependencias opcionales:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements_opcionales.txt
```

- `graficas.py`: genera gráficas PNG de velocidad y distancia desde un Excel exportado. Uso: `.\.venv\Scripts\python.exe graficas.py medicion.xlsx`.
- `agilent_33220a.py`: proporciona una clase para consultar la identificación del generador mediante VISA. Requiere un backend VISA compatible con la conexión utilizada.
- `calculos.py`: incluye conversiones y estadísticas auxiliares.

## Configuración y archivos generados

Las preferencias se guardan localmente en `config_ligero.json`. La dirección TCP y los puertos COM iniciales son valores de ejemplo; configure los correspondientes a cada instalación.

Los resultados se guardan en la carpeta seleccionada; el destino predeterminado es `Documents/exportaciones_lsv` dentro del perfil del usuario. Los respaldos se almacenan en `respaldos_jsonl`.

El archivo `.gitignore` excluye preferencias locales, entornos virtuales, capturas, registros y resultados para evitar incorporarlos al repositorio.

## Comprobación del código

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
