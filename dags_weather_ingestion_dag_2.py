import pendulum
import requests
import json

from airflow.decorators import dag, task
from airflow.providers.google.cloud.hooks.gcs import GCSHook
#   1: Importar a biblioteca   do Secret Manager e o GoogleBaseHook
from airflow.providers.google.common.hooks.base_google import GoogleBaseHook
from google.cloud import secretmanager

GCS_BUCKET_NAME = "weather-advice-ai" # Substitua pelo nome do seu bucket
CITY_NAME = "Sao Paulo"

@dag(
    dag_id="daily_weather_to_gcs",
    start_date=pendulum.datetime(2025, 8, 17, tz="America/Sao_Paulo"),
    schedule="0 7 * * *",  # Executa todos os dias às 7:00 da  
    catchup=False,
    tags=["weather", "gcp"],
)
def daily_weather_ingestion():
    @task
    def get_weather_data() -> str:
        """Busca os dados do tempo da API OpenWeatherMap."""
        print(f"Buscando dados do tempo para {CITY_NAME}...")
        
        # --- Lógica para buscar o segredo usando a biblioteca padrão do GCP ---
        
        # Primeiro, pegamos o ID do projeto a partir da conexão padrão do Airflow com o GCP
        gcp_hook = GoogleBaseHook(gcp_conn_id="google_cloud_default")
        project_id = gcp_hook.project_id

        # Agora, usamos o cliente do Secret Manager, como no Cloud Run
        client = secretmanager.SecretManagerServiceClient()
        secret_name = f"projects/{project_id}/secrets/OPENWEATHER_API_KEY/versions/latest"
        
        print(f"Buscando segredo: {secret_name}")
        response = client.access_secret_version(request={"name": secret_name})
        api_key = response.payload.data.decode("UTF-8")

        base_url = "http://api.openweathermap.org/data/2.5/weather"
        params = {
            'q': f"{CITY_NAME},BR",
            'appid': api_key,
            'units': 'metric',
            'lang': 'pt_br'
        }
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        print("Dados obtidos com sucesso.")
        return json.dumps(response.json())

    @task
    def upload_to_gcs(file_content: str, execution_date: str):
        """Salva o conteúdo JSON em um arquivo no Google Cloud Storage."""
        formatted_date = pendulum.parse(execution_date).format("YYYYMMDD")
        file_name = f"sao_paulo_{formatted_date}.json"
        
        print(f"Fazendo upload para gs://{GCS_BUCKET_NAME}/{file_name}...")
        gcs_hook = GCSHook(gcp_conn_id="google_cloud_default")
        gcs_hook.upload(
            bucket_name=GCS_BUCKET_NAME,
            object_name=file_name,
            data=file_content,
            mime_type="application/json",
        )
        print("Upload concluido.")

    weather_json = get_weather_data()
    upload_to_gcs(file_content=weather_json, execution_date="{{ ds }}")

daily_weather_ingestion()