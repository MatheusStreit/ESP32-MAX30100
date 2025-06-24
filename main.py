from time import sleep, ticks_ms, ticks_diff
from machine import Pin, I2C, reset
import max30100
import urequests
import gc
import network
import sys

# --- Wi-Fi ---
WIFI_SSID = "moto_g54"
WIFI_PASSWORD = "motorola"

def conectar_wifi():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print('[INFO] Conectando ao Wi-Fi...')
        wlan.active(True)
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        tentativas = 0
        while not wlan.isconnected() and tentativas < 15:
            sleep(1)
            tentativas += 1
        if not wlan.isconnected():
            print('[ERRO] Falha ao conectar no Wi-Fi.')
            return None
    print('[INFO] Conectado. IP:', wlan.ifconfig()[0])
    return wlan

wlan = conectar_wifi()
if wlan is None:
    raise RuntimeError("Wi-Fi não conectado")

# --- MAC do monitor ---
mac_bytes = wlan.config('mac')
mac_address = ':'.join(['%02X' % b for b in mac_bytes])
print("[INFO] MAC:", mac_address)

# --- Configurações ---
SERVER_URL = "http://192.168.179.103:5000/api/atualizar"
DURACAO_COLETA_MS = 6000
INTERVALO_LEITURA = 0.25  # segundos

# --- Timer para reinício automático ---
TEMPO_REINICIO_MS = 5 * 60 * 1000  # 5 minutos
ultimo_reinicio = ticks_ms()

# --- Sensor ---
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = None

def inicializar_sensor():
    global sensor
    try:
        sensor = max30100.MAX30100(i2c=i2c)
        sensor.set_led_current(14.2, 14.2)
        sensor.enable_spo2()
        print("[INFO] Sensor MAX30100 inicializado.")
    except Exception as e:
        print(f"[ERRO] Falha ao inicializar sensor: {e}")
        sensor = None

inicializar_sensor()

# --- Funções auxiliares ---
def detectar_picos(dados_ir):
    picos = []
    for i in range(1, len(dados_ir) - 1):
        ir_anterior = dados_ir[i - 1][0]
        ir_atual = dados_ir[i][0]
        ir_proximo = dados_ir[i + 1][0]
        if ir_atual > ir_anterior and ir_atual > ir_proximo:
            picos.append(dados_ir[i][1])  # timestamp do pico
    return picos

def calcular_bpm(picos):
    if len(picos) < 2:
        return None
    intervalos = [ticks_diff(picos[i + 1], picos[i]) for i in range(len(picos) - 1)]
    media_intervalo = sum(intervalos) / len(intervalos)
    bpm = 60000 / media_intervalo
    return round(bpm)

def calcular_spo2(amostras):
    valores_spo2 = []
    for ir, red, _ in amostras:
        if ir == 0:
            continue
        razao = red / ir
        spo2 = 110 - 25 * razao
        valores_spo2.append(spo2)
    if not valores_spo2:
        return None
    media_spo2 = sum(valores_spo2) / len(valores_spo2)
    return max(0, min(100, round(media_spo2)))

# --- Loop principal ---
while True:
    try:
        # Verificação de tempo para reinício automático
        if ticks_diff(ticks_ms(), ultimo_reinicio) > TEMPO_REINICIO_MS:
            print("[INFO] Reiniciando ESP32 para liberar memória...")
            sleep(1)
            reset()

        if sensor is None:
            inicializar_sensor()
            if sensor is None:
                sleep(2)
                continue

        amostras = []
        inicio = ticks_ms()

        # Coleta de dados por 6 segundos
        while ticks_diff(ticks_ms(), inicio) < DURACAO_COLETA_MS:
            sensor.read_sensor()
            ir = sensor.ir
            red = sensor.red
            agora = ticks_ms()
            if ir > 5000:
                amostras.append((ir, red, agora))
                if len(amostras) > 100:
                    amostras.pop(0)
            sleep(INTERVALO_LEITURA)
            gc.collect()

        if len(amostras) < 10:
            print("[WARN] Poucas amostras coletadas, ignorando ciclo.")
            del amostras
            gc.collect()
            continue

        dados_ir_com_tempo = [(am[0], am[2]) for am in amostras]
        picos = detectar_picos(dados_ir_com_tempo)
        bpm = calcular_bpm(picos)
        spo2 = calcular_spo2(amostras)

        print(f"[INFO] BPM={bpm}, SpO2={spo2}%")

        if bpm is not None and spo2 is not None:
            payload = {
                "mac": mac_address,
                "batimento": bpm,
                "spo2": spo2
            }

            try:
                gc.collect()
                headers = {'Content-Type': 'application/json'}
                resposta = urequests.post(SERVER_URL, json=payload, headers=headers)
                if resposta.status_code == 200:
                    print("[INFO] Dados enviados com sucesso.")
                else:
                    print(f"[ERRO] Resposta do servidor: {resposta.status_code}")
            except Exception as erro_envio:
                print(f"[ERRO] Falha ao enviar dados: {erro_envio}")
            finally:
                try:
                    resposta.close()
                except:
                    pass
                gc.collect()

        # Limpeza de variáveis
        del amostras, dados_ir_com_tempo, picos, bpm, spo2, payload
        gc.collect()

    except Exception as e:
        sys.print_exception(e)
        gc.collect()
        sleep(1)
