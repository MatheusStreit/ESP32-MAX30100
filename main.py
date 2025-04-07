import network
import socket
from machine import Pin, I2C
from time import sleep, ticks_ms, ticks_diff
from max30100 import MAX30100

# ========= CONFIG Wi-Fi =========
SSID = 'BUDD_VISITANTES'
SENHA = 'budd3m3y3r@1951'

print("Conectando ao Wi-Fi...")
wifi = network.WLAN(network.STA_IF)
wifi.active(True)
wifi.connect(SSID, SENHA)

while not wifi.isconnected():
    sleep(0.5)
print("Conectado! IP:", wifi.ifconfig()[0])

# ========= SENSOR =========
i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = MAX30100(i2c=i2c)
sensor.set_led_current(27.1, 27.1)

red_buffer = []
ir_buffer = []
bpm_buffer = []

ultimo_valor_ir = 0
penultimo_valor_ir = 0
last_peak_time = None

bpm = 0
oxigenacao = 0

# Ajuste para detecção de pico
PICO_LIMIAR = 500

# Função de média móvel
def media_movel(buffer, novo_valor, tamanho):
    buffer.append(novo_valor)
    if len(buffer) > tamanho:
        buffer.pop(0)
    return sum(buffer) / len(buffer)

# Função para detectar pico melhorada
def detectar_pico(valor_atual, ultimo_valor, penultimo_valor):
    return (penultimo_valor < ultimo_valor > valor_atual) and (ultimo_valor - penultimo_valor > PICO_LIMIAR)

# ========= WEB SERVER =========
html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Monitor de Saúde - ESP32</title>
    <meta http-equiv="refresh" content="1">
    <style>
        body {{ font-family: Arial; text-align: center; }}
        .card {{
            display: inline-block;
            background: #f2f2f2;
            padding: 20px;
            margin-top: 40px;
            border-radius: 15px;
            box-shadow: 2px 2px 12px #aaa;
        }}
        h1 {{ color: #333; }}
        h2 {{ color: #0077cc; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>💓 Monitor de Saúde - ESP32</h1>
        <h2>BPM: {bpm:.0f}</h2>
        <h2>Oxigenação: {spo2:.2f}</h2>
    </div>
</body>
</html>
"""

# Cria socket web
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)
print("Servidor iniciado em http://{}/".format(wifi.ifconfig()[0]))

# ========= LOOP principal =========
while True:
    try:
        # ===== Sensor Reading =====
        sensor.read_sensor()
        red = media_movel(red_buffer, sensor.red, 10)
        ir = media_movel(ir_buffer, sensor.ir, 10)
        oxigenacao = red / ir if ir != 0 else 0
        
        print(f"IR: {ir}, Red: {red}")
        print(f"Último IR: {ultimo_valor_ir}, Penúltimo IR: {penultimo_valor_ir}")
        
        if detectar_pico(ir, ultimo_valor_ir, penultimo_valor_ir):
            agora = ticks_ms()
            if last_peak_time is not None:
                intervalo = ticks_diff(agora, last_peak_time)
                if 300 < intervalo < 2000:  # Frequência entre 30 e 200 BPM
                    bpm_inst = 60000 / intervalo
                    bpm_buffer.append(bpm_inst)
                    if len(bpm_buffer) > 5:
                        bpm_buffer.pop(0)
                    print(f"Pico detectado! BPM instantâneo: {bpm_inst}")
            last_peak_time = agora
        
        penultimo_valor_ir = ultimo_valor_ir
        ultimo_valor_ir = ir
        
        bpm = sum(bpm_buffer) / len(bpm_buffer) if bpm_buffer else 0
        print(f"BPM final exibido: {bpm:.2f}")
        
        # ===== Web Server Response =====
        conn, addr = s.accept()
        print("Cliente conectado:", addr)
        request = conn.recv(1024)
        response = html.format(bpm=bpm, spo2=oxigenacao)
        conn.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
        conn.sendall(response)
        conn.close()

        sleep(0.1)

    except Exception as e:
        print("Erro:", e)
        sleep(1)
