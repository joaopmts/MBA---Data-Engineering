import boto3
import json
import random
import time
from datetime import datetime

print("=" * 60)
print("PRODUTOR DE DADOS - SIMULADOR DE PEDIDOS")
print("=" * 60)

kinesis = boto3.client('kinesis', region_name='sa-east-1')
STREAM_NAME = 'pedidos-ifood-stream'

RESTAURANTES = [
    "Outback - Paulista",
    "Madero - Eldorado",
    "China in Box - Moema",
    "Spoleto - Faria Lima",
    "Braz Pizzaria - Jardins",
    "Gendai - Brooklin"
]

BAIRROS = [
    "Vila Madalena",
    "Pinheiros",
    "Itaim Bibi",
    "Jardins",
    "Moema",
    "Brooklin"
]

STATUS_LISTA = ["confirmado", "preparando", "saiu_entrega", "cancelado"]
STATUS_PESOS = [40, 30, 20, 10]

def escolher_status():
    return random.choices(STATUS_LISTA, weights=STATUS_PESOS, k=1)[0]

def gerar_pedido():
    pedido = {
        "pedido_id": f"PED{random.randint(100000, 999999)}",
        "timestamp": datetime.now().isoformat(),
        "restaurante": random.choice(RESTAURANTES),
        "bairro": random.choice(BAIRROS),
        "valor": round(random.uniform(25.0, 150.0), 2),
        "status": escolher_status()
    }
    return pedido

def enviar_pedido(pedido):
    try:
        kinesis.put_record(
            StreamName=STREAM_NAME,
            Data=json.dumps(pedido),
            PartitionKey=pedido["pedido_id"]
        )
        return True
    except Exception as e:
        print(f"Erro: {e}")
        return False

print(f"Stream: {STREAM_NAME}")
print("Gerando pedidos... (Ctrl+C para parar)")
print("-" * 60)

contador = 0
valor_total = 0.0

try:
    while contador < 50:
        pedido = gerar_pedido()
        
        if enviar_pedido(pedido):
            contador += 1
            valor_total += pedido["valor"]
            
            marca = "[OK]" if pedido["status"] != "cancelado" else "[XX]"
            
            print(f"{marca} #{contador:02d} | {pedido['pedido_id']} | "
                  f"{pedido['status']:12s} | R$ {pedido['valor']:6.2f} | "
                  f"{pedido['restaurante']}")
        
        time.sleep(1)
    
    print("-" * 60)
    print(f"Finalizado: {contador} pedidos enviados")
    print(f"Valor total: R$ {valor_total:.2f}")

except KeyboardInterrupt:
    print(f"\nParado: {contador} pedidos enviados")
