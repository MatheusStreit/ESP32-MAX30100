from time import sleep, ticks_ms, ticks_diff
from machine import Pin, I2C
import max30100
import gc

i2c = I2C(0, scl=Pin(22), sda=Pin(21))
sensor = None

def inicializar_sensor():
    global sensor
    try:
        sensor = max30100.MAX30100(i2c=i2c)
        sensor.set_led_current(11.0, 27.1)
        sensor.enable_spo2()
        print("[INFO] Sensor MAX30100 inicializado.")
    except Exception as e:
        print(f"Erro ao inicializar sensor: {e}")
        sensor = None

inicializar_sensor()

def calcular_bpm_spo2(duracao=3):
    global sensor
    ir_buffer = []
    window_size = 2
    ultimo_batimento = None
    contagem = 0
    threshold = 200
    inicio = ticks_ms()

    while ticks_diff(ticks_ms(), inicio) < duracao * 1000:
        try:
            if sensor is None:
                print("Sensor não inicializado corretamente. Reiniciando...")
                inicializar_sensor()
                if sensor is None:
                    sleep(2)
                    continue
            sensor.read_sensor()
            ir = sensor.ir
            red = sensor.red
        except Exception as e:
            print("Erro ao ler sensor:", e)
            inicializar_sensor()
            sleep(2)
            continue

        if ir < 5000:
            continue

        ir_buffer.append(ir)
        if len(ir_buffer) > window_size:
            ir_buffer.pop(0)
        ir_suavizado = sum(ir_buffer) / len(ir_buffer)

        agora = ticks_ms()
        if ir > ir_suavizado + threshold and (ultimo_batimento is None or ticks_diff(agora, ultimo_batimento) > 400):
            if ultimo_batimento is not None:
                contagem += 1
            ultimo_batimento = agora

        gc.collect()
        sleep(0.01)

    tempo_total = ticks_diff(ticks_ms(), inicio)
    if contagem > 0 and tempo_total > 0:
        bpm = int((contagem * 60000) / tempo_total)
        erro = int(bpm * 0.05)
        bpm_min = bpm - erro
        bpm_max = bpm + erro
        print
