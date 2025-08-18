import os
import json
from flask import Flask, request

# Importações para os serviços do Google Cloud
from google.cloud import storage
import vertexai
from vertexai.generative_models import GenerativeModel
from google.cloud import secretmanager

# Importação para o serviço de SMS
from twilio.rest import Client

app = Flask(__name__)

# Função para buscar segredos de forma segura
def get_secret(secret_id, project_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

@app.route("/", methods=["POST"])
def process_weather_file_with_gemini():
    # --- MUDANÇA PRINCIPAL: Processar o evento direto do Cloud Storage ---
    
    # A requisição inteira é o payload do evento que vimos nos logs.
    event_payload = request.get_json()
    
    # Verificação de segurança para garantir que o payload tem as chaves que precisamos.
    if not event_payload or "bucket" not in event_payload or "name" not in event_payload:
        print(f"Payload inválido ou sem os campos 'bucket'/'name'. Payload: {event_payload}")
        return "Payload de evento Cloud Storage inválido", 400

    # Extrai as informações diretamente do payload.
    bucket_name = event_payload["bucket"]
    file_name = event_payload["name"]
    
    print(f"Novo arquivo detectado: {file_name} no bucket {bucket_name}")
    # --- FIM DA MUDANÇA ---

    # O resto do código continua como planejado...
    
    # 2. Ler o arquivo do Cloud Storage
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    weather_json_str = blob.download_as_string().decode('utf-8')
    print("Conteúdo do arquivo lido com sucesso.")

    # 3. Chamar o Gemini no Vertex AI para resumir os dados
    #project_id = os.environ.get("GCP_PROJECT")
    location = "us-central1"

    project_id="523376765860"

    vertexai.init(project=project_id, location=location)
    model = GenerativeModel("gemini-2.5-flash")
    
    prompt_para_gemini = f"""
    Você é um assistente de meteorologia criativo e amigável.
    Com base nos seguintes dados JSON do clima:
    ---
    {weather_json_str}
    ---
    Crie uma mensagem de SMS curta (máximo de 150 caracteres), descontraido, formal  e útil.
    Considerar a estação do ano da data enviada.
    A mensagem deve incluir a temperatura principal, a condição do tempo e uma sugestão de roupa.
    Responda apenas com o texto da mensagem a ser enviada.
    LEMBRANDO: Considerar a estação do ano na data apresentada.
    """
    
    print("Chamando o Gemini no Vertex AI...")
    response = model.generate_content(prompt_para_gemini)
    summary = response.text
    print(f"Resumo recebido do Gemini: {summary}")
    
    # 4. Enviar o resumo por SMS via Twilio
    account_sid = get_secret("TWILIO_ACCOUNT_SID", project_id)
    auth_token = get_secret("TWILIO_AUTH_TOKEN", project_id)
    from_number = get_secret("TWILIO_FROM_NUMBER", project_id)
    to_number = get_secret("TWILIO_TO_NUMBER", project_id)
    
    print(f"Enviando SMS para {to_number}...")
    twilio_client = Client(account_sid, auth_token)
    message = twilio_client.messages.create(
        body=summary, from_=from_number, to=to_number
    )
    print(f"SMS enviado com sucesso! SID: {message.sid}")

    # A "pasta" para onde o arquivo será movido após o processamento 
    destination_bucket_name = "weather_processed_file"
    destination_bucket = storage_client.bucket(destination_bucket_name)


    destination_blob_name = f"{file_name}"


    # Copia o blob
    new_blob = bucket.copy_blob(blob, destination_bucket, destination_blob_name)

    # Exclui o blob original
    blob.delete()

    print(f"Destination folder {destination_blob_name}")


    return "Processamento com Gemini concluído.", 204


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
